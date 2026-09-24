#!/usr/bin/env python3
"""
FLUX WMS 数据源SQL写入工具
将用户配置的查询SQL写入系统，涉及多表联动写入：
  1. DEV_UDFFUNCFG — 更新版本号（乐观锁）
  2. DEV_UDFFUNCFG_QUERY — 插入/更新SQL配置
  3. BSM_FUNCTION_PAGE — 删除旧的再插入新的
  4. BSM_FUNCTION_PAGE_ML — 删除旧的再插入新的多语言

关键设计：
  - 版本号和乐观锁必须实时从数据库获取，禁止硬编码
  - DELETE + INSERT 必须作为事务执行
"""

import json
import os
import argparse
import sys
from pathlib import Path
from datetime import datetime

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database

# 调试输出开关：设置环境变量 FLUX_DEBUG=1 启用
DEBUG = os.environ.get('FLUX_DEBUG', '').lower() in ('1', 'true')


# ============================================================
# SQL 完整性校验
# ============================================================

def validate_sql(sql: str) -> bool:
    """
    验证SQL是否完整，避免命令行转义导致SQL被截断。

    检查项：
    1. 最小长度（至少50个字符）
    2. 必须包含 SELECT 和 FROM 关键字
    3. 必须包含 ${WHERE} 占位符（FLUX WMS 系统要求）

    返回: True 表示校验通过
    异常: ValueError 表示校验失败
    """
    if not sql or not sql.strip():
        raise ValueError("SQL 不能为空")

    min_length = 50
    if len(sql) < min_length:
        raise ValueError(
            f"SQL 长度不足：{len(sql)} < {min_length}。"
            f"可能是命令行转义导致SQL被截断。建议使用 --sql-file 参数从文件读取SQL。"
        )

    upper_sql = sql.upper()
    required_keywords = ['SELECT', 'FROM']
    for keyword in required_keywords:
        if keyword not in upper_sql:
            raise ValueError(f"SQL 缺少必要关键字：{keyword}")

    # 检查是否包含 ${WHERE} 占位符
    if '${WHERE}' not in sql:
        raise ValueError("SQL 缺少 ${WHERE} 占位符（FLUX WMS 系统要求）")

    return True


def read_sql_from_file(file_path: str) -> str:
    """
    从文件读取SQL，去除注释和多余空白。

    使用场景：
    - 当SQL包含特殊字符（$、单引号、反引号等）时
    - 命令行传递会导致转义或截断问题
    - 从文件读取可以完全避免转义问题
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"SQL 文件不存在: {file_path}")

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 过滤注释行（以 -- 开头）
    sql_lines = [line for line in lines if not line.strip().startswith('--')]

    # 合并行并去除多余空白
    sql = ' '.join(sql_lines).strip()

    # 压缩多个空格为单个空格
    while '  ' in sql:
        sql = sql.replace('  ', ' ')

    return sql


# ============================================================
# 步骤1：实时获取版本号和乐观锁
# ============================================================

def get_current_version(cursor, org_id: str, function_id: str) -> dict:
    """
    实时查询当前版本号、乐观锁标记和布局模式。
    这是写入前必须执行的第一步，禁止硬编码版本号。

    返回: {'currentversion': '101.00000000', 'oprseqflag': '20260605...', 'layoutpattern': 'SINGLE'}
    """
    cursor.execute("""
        SELECT currentversion, oprseqflag, layoutpattern
        FROM DEV_UDFFUNCFG
        WHERE organizationid = :org_id AND functionid = :func_id
    """, {'org_id': org_id, 'func_id': function_id})

    result = cursor.fetchone()
    if result is None:
        raise ValueError(f"功能 {function_id} 在 DEV_UDFFUNCFG 中不存在，请先创建功能。")

    oprseqflag = result[1]
    # 调试输出：显示 oprseqflag 的十六进制表示，排查隐藏字符
    if DEBUG and oprseqflag:
        hex_repr = oprseqflag.encode('utf-8').hex()
        print(f"  [DEBUG] oprseqflag 长度: {len(oprseqflag)}")
        print(f"  [DEBUG] oprseqflag HEX: {hex_repr}")
        print(f"  [DEBUG] oprseqflag 首字符: '{oprseqflag[0]}' (ord={ord(oprseqflag[0])})")
        print(f"  [DEBUG] oprseqflag 末字符: '{oprseqflag[-1]}' (ord={ord(oprseqflag[-1])})")

    return {
        'currentversion': result[0],
        'oprseqflag': oprseqflag,
        'layoutpattern': result[2]
    }


def increment_version(current_version: str) -> str:
    """
    版本号递增：'101.00000000' → '102.00000000'
    """
    try:
        ver_num = int(float(current_version))
        return f"{ver_num + 1}.00000000"
    except (ValueError, TypeError):
        # 兜底：如果版本号格式异常，使用时间戳
        return f"{int(datetime.now().timestamp())}.00000000"


def generate_opr_seq_flag(function_id: str = 'C0102') -> str:
    """
    生成操作流水标记，格式：时间戳RA序号[功能ID]
    示例：'20260605102730000275RA010000222114[C0102]'

    参数:
      function_id: 功能编号，默认为 'C0102'

    返回: 操作流水标记字符串
    """
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d%H%M%S%f')[:22]  # 22位时间戳
    # 使用传入的功能ID，与系统生成格式保持一致
    return f"{timestamp}RA010000222114[{function_id}]"


# ============================================================
# 步骤2：更新 DEV_UDFFUNCFG 版本号（乐观锁）
# ============================================================

def update_function_version(cursor, org_id: str, function_id: str,
                            new_version: str, new_opr_seq: str,
                            old_opr_seq: str, user: str,
                            layoutpattern: str) -> int:
    """
    更新功能版本号，使用旧的 oprseqflag 做乐观锁。
    如果返回 0 行，说明被其他会话修改过，需要重新获取版本号。

    参数:
      layoutpattern: 从数据库查询到的布局模式，保留原值不修改

    返回: 影响行数
    """
    cursor.execute("""
        UPDATE DEV_UDFFUNCFG
        SET currentversion = :new_version,
            oprseqflag = :new_opr_seq,
            editwho = :edit_who,
            layoutpattern = :layoutpattern,
            edittime = SYSDATE
        WHERE organizationid = :org_id
          AND functionid = :func_id
          AND oprseqflag = :old_opr_seq
    """, {
        'new_version': new_version,
        'new_opr_seq': new_opr_seq,
        'edit_who': user,
        'layoutpattern': layoutpattern,
        'org_id': org_id,
        'func_id': function_id,
        'old_opr_seq': old_opr_seq
    })

    rowcount = cursor.rowcount
    if rowcount == 0:
        # 诊断输出：乐观锁失败时显示详细信息
        print(f"\n  [诊断] 乐观锁 UPDATE 失败，影响行数=0")
        print(f"  [诊断] WHERE 条件: org={org_id}, func={function_id}")
        print(f"  [诊断] old_opr_seq='{old_opr_seq}' (len={len(old_opr_seq)})")
        # 重新查询当前值进行比对
        cursor.execute("""
            SELECT currentversion, oprseqflag
            FROM DEV_UDFFUNCFG
            WHERE organizationid = :org_id AND functionid = :func_id
        """, {'org_id': org_id, 'func_id': function_id})
        current = cursor.fetchone()
        if current:
            print(f"  [诊断] 当前数据库值: version={current[0]}, oprseqflag='{current[1]}' (len={len(current[1]) if current[1] else 0})")
            if current[1] == old_opr_seq:
                print(f"  [诊断] 值完全匹配！可能是绑定变量问题")
            else:
                print(f"  [诊断] 值不匹配！")
                # 逐字符比对
                db_val = current[1] or ''
                for i in range(min(len(db_val), len(old_opr_seq))):
                    if db_val[i] != old_opr_seq[i]:
                        print(f"  [诊断] 第 {i} 个字符不同: db='{db_val[i]}'({ord(db_val[i])}) vs param='{old_opr_seq[i]}'({ord(old_opr_seq[i])})")
                        break
        else:
            print(f"  [诊断] 记录不存在！")

    return rowcount


# ============================================================
# 步骤3：写入 DEV_UDFFUNCFG_QUERY（SQL配置）
# ============================================================

def check_query_exists(cursor, org_id: str, function_id: str, widget_name: str) -> bool:
    """检查数据源SQL配置是否已存在"""
    cursor.execute("""
        SELECT COUNT(*) FROM DEV_UDFFUNCFG_QUERY
        WHERE organizationid = :org_id
          AND functionid = :func_id
          AND widgetname = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})

    return cursor.fetchone()[0] > 0


def insert_query_config(cursor, org_id: str, function_id: str,
                        widget_name: str, json_data: str,
                        version: str, opr_seq: str, user: str) -> int:
    """插入数据源SQL配置，返回影响行数"""
    cursor.execute("""
        INSERT INTO DEV_UDFFUNCFG_QUERY (
            organizationid, functionid, widgetname, jsondata,
            activeflag, currentversion, oprseqflag,
            addwho, editwho, addtime, edittime
        ) VALUES (
            :org_id, :func_id, :widget_name, :json_data,
            'Y', :version, :opr_seq,
            :add_who, :edit_who, SYSDATE, SYSDATE
        )
    """, {
        'org_id': org_id,
        'func_id': function_id,
        'widget_name': widget_name,
        'json_data': json_data,
        'version': version,
        'opr_seq': opr_seq,
        'add_who': user,
        'edit_who': user
    })
    return cursor.rowcount


def update_query_config(cursor, org_id: str, function_id: str,
                        widget_name: str, json_data: str,
                        version: str, opr_seq: str, user: str) -> int:
    """更新已有的数据源SQL配置，返回影响行数"""
    cursor.execute("""
        UPDATE DEV_UDFFUNCFG_QUERY
        SET jsondata = :json_data,
            currentversion = :version,
            oprseqflag = :opr_seq,
            editwho = :edit_who,
            edittime = SYSDATE
        WHERE organizationid = :org_id
          AND functionid = :func_id
          AND widgetname = :widget_name
    """, {
        'json_data': json_data,
        'version': version,
        'opr_seq': opr_seq,
        'edit_who': user,
        'org_id': org_id,
        'func_id': function_id,
        'widget_name': widget_name
    })
    return cursor.rowcount


# ============================================================
# 步骤4：写入 BSM_FUNCTION_PAGE（页面注册）
# ============================================================

def delete_function_page(cursor, org_id: str, function_id: str):
    """删除旧的页面注册记录"""
    # 删除多语言记录（先删子表）
    cursor.execute("""
        DELETE FROM BSM_FUNCTION_PAGE_ML
        WHERE organizationid = :org_id
          AND functionid = :func_id
          AND functionlevel = 'ALL'
    """, {'org_id': org_id, 'func_id': function_id})

    # 删除主表记录
    cursor.execute("""
        DELETE FROM BSM_FUNCTION_PAGE
        WHERE organizationid = :org_id
          AND functionid = :func_id
          AND functionlevel = 'ALL'
    """, {'org_id': org_id, 'func_id': function_id})


def insert_function_page(cursor, org_id: str, function_id: str,
                         table_id: str, opr_seq: str, user: str):
    """插入页面注册记录"""
    cursor.execute("""
        INSERT INTO BSM_FUNCTION_PAGE (
            organizationid, functionid, tableid, functionlevel,
            currentversion, oprseqflag,
            addwho, editwho, addtime, edittime
        ) VALUES (
            :org_id, :func_id, :table_id, 'ALL',
            '100.00000000', :opr_seq,
            :add_who, :edit_who, SYSDATE, SYSDATE
        )
    """, {
        'org_id': org_id,
        'func_id': function_id,
        'table_id': table_id,
        'opr_seq': opr_seq,
        'add_who': user,
        'edit_who': user
    })


def insert_function_page_ml(cursor, org_id: str, function_id: str,
                            table_id: str, page_descr: str,
                            language_id: str, opr_seq: str, user: str):
    """插入页面多语言描述"""
    cursor.execute("""
        INSERT INTO BSM_FUNCTION_PAGE_ML (
            organizationid, functionid, tableid, functionlevel,
            pagedescr, languageid, currentversion, oprseqflag,
            addwho, editwho, addtime, edittime
        ) VALUES (
            :org_id, :func_id, :table_id, 'ALL',
            :page_descr, :language_id, '100.00000000', :opr_seq,
            :add_who, :edit_who, SYSDATE, SYSDATE
        )
    """, {
        'org_id': org_id,
        'func_id': function_id,
        'table_id': table_id,
        'page_descr': page_descr,
        'language_id': language_id,
        'opr_seq': opr_seq,
        'add_who': user,
        'edit_who': user
    })


# ============================================================
# 验证写入结果
# ============================================================

def verify_insertion(cursor, org_id: str, function_id: str, widget_name: str, expected_sql: str = None):
    """验证所有表的写入结果，包括校验SQL内容是否正确"""
    print("\n" + "=" * 60)
    print("写入验证报告")
    print("=" * 60)

    # 验证1：DEV_UDFFUNCFG 版本号
    cursor.execute("""
        SELECT currentversion, layoutpattern, editwho,
               TO_CHAR(edittime, 'yyyy-MM-dd HH24:mi:ss') AS edittime
        FROM DEV_UDFFUNCFG
        WHERE organizationid = :org_id AND functionid = :func_id
    """, {'org_id': org_id, 'func_id': function_id})
    row = cursor.fetchone()
    if row:
        print(f"\n1. DEV_UDFFUNCFG（功能主表）:")
        print(f"   版本号: {row[0]}")
        print(f"   布局模式: {row[1]}")
        print(f"   编辑人: {row[2]}")
        print(f"   编辑时间: {row[3]}")

    # 验证2+3：DEV_UDFFUNCFG_QUERY — 读取所有记录，逐一校验
    cursor.execute("""
        SELECT widgetname, activeflag, currentversion,
               LENGTH(jsondata) AS json_len,
               addwho, TO_CHAR(addtime, 'yyyy-MM-dd HH24:mi:ss') AS addtime,
               JSON_VALUE(jsondata, '$.sqlMain') AS saved_sql,
               JSON_VALUE(jsondata, '$.tableName') AS source_table,
               JSON_VALUE(jsondata, '$.pkey') AS primary_keys
        FROM DEV_UDFFUNCFG_QUERY
        WHERE organizationid = :org_id AND functionid = :func_id
        ORDER BY widgetname
    """, {'org_id': org_id, 'func_id': function_id})
    rows = cursor.fetchall()
    if rows:
        print(f"\n2. DEV_UDFFUNCFG_QUERY（数据源SQL）: 共 {len(rows)} 条记录")
        for r in rows:
            db_widget = r[0]
            saved_sql = r[6]  # JSON_VALUE(jsondata, '$.sqlMain')
            tbl = r[7]        # JSON_VALUE(jsondata, '$.tableName')
            pkey = r[8]       # JSON_VALUE(jsondata, '$.pkey')
            print(f"  [{db_widget}] 活动={r[1]}, 版本={r[2]}, JSON长度={r[3]} 字节")
            print(f"   新增人={r[4]}, 新增时间={r[5]}, 数据源表={tbl}, 主键={pkey}")

            # 校验 SQL 内容：匹配当前写入的组件名时，对比预期 SQL
            if db_widget == widget_name and expected_sql:
                if saved_sql and saved_sql.strip() == expected_sql.strip():
                    print(f"    [OK] sqlMain 校验通过")
                else:
                    preview_expected = expected_sql[:80] + '...' if len(expected_sql) > 80 else expected_sql
                    preview_actual = (saved_sql[:80] + '...' if saved_sql and len(saved_sql) > 80 else saved_sql) if saved_sql else 'NULL'
                    print(f"    [ERROR] sqlMain 校验失败！")
                    print(f"      预期: {preview_expected}")
                    print(f"      实际: {preview_actual}")
                    raise RuntimeError(
                        f"sqlMain 写入验证失败: {db_widget}，"
                        f"预期SQL与数据库保存的SQL不一致"
                    )
            elif saved_sql:
                sql_preview = saved_sql[:80] + '...' if len(saved_sql) > 80 else saved_sql
                print(f"   保存SQL: {sql_preview}")

    # 验证4：BSM_FUNCTION_PAGE
    cursor.execute("""
        SELECT tableid, functionlevel
        FROM BSM_FUNCTION_PAGE
        WHERE organizationid = :org_id AND functionid = :func_id
    """, {'org_id': org_id, 'func_id': function_id})
    row = cursor.fetchone()
    if row:
        print(f"\n3. BSM_FUNCTION_PAGE（页面注册）:")
        print(f"   数据表: {row[0]}")
        print(f"   功能级别: {row[1]}")

    # 验证5：BSM_FUNCTION_PAGE_ML
    cursor.execute("""
        SELECT languageid, pagedescr
        FROM BSM_FUNCTION_PAGE_ML
        WHERE organizationid = :org_id AND functionid = :func_id
        ORDER BY languageid
    """, {'org_id': org_id, 'func_id': function_id})
    rows = cursor.fetchall()
    if rows:
        print(f"\n4. BSM_FUNCTION_PAGE_ML（多语言）:")
        for r in rows:
            print(f"   {r[0]}: {r[1]}")

    print("\n" + "=" * 60)


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='FLUX WMS 数据源SQL写入工具（多表联动）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
写入顺序（严格按此执行）：
  1. DEV_UDFFUNCFG — 更新版本号（乐观锁）
  2. DEV_UDFFUNCFG_QUERY — 插入/更新SQL配置
  3. BSM_FUNCTION_PAGE — 删除旧的再插入新的
  4. BSM_FUNCTION_PAGE_ML — 删除旧的再插入新的多语言

SQL 输入方式（二选一）：
  --sql "SQL语句"         直接传递SQL（简单SQL，无特殊字符）
  --sql-file path.sql     从文件读取SQL（推荐，避免命令行转义问题）

示例：
  # 示例1：简单SQL直接传递
  python insert_query_config.py C0104_AZTT_PURSGROUP \\
    --sql "SELECT A.ORGANIZATIONID, A.CUSTOMERID FROM UDF_PURCHASINGGROUP A WHERE 1=1 \${WHERE}" \\
    --table-name UDF_PURCHASINGGROUP \\
    --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE" \\
    --page-descr-zh "主信息" \\
    --page-descr-en "Main Information"

  # 示例2：复杂SQL从文件读取（推荐）
  python insert_query_config.py C0104_AZTT_PURSGROUP \\
    --sql-file outputs/C0104_AZTT_PURSGROUP.sql \\
    --table-name UDF_PURCHASINGGROUP \\
    --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE" \\
    --page-descr-zh "主信息" \\
    --page-descr-en "Main Information"

  # 示例3：Dry-run 模式（仅打印，不执行）
  python insert_query_config.py C0104_AZTT_PURSGROUP \\
    --sql-file outputs/C0104_AZTT_PURSGROUP.sql \\
    --table-name UDF_PURCHASINGGROUP \\
    --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE" \\
    --dry-run
        """
    )

    parser.add_argument('function_id', help='功能编号 (FUNCTIONID)')

    # SQL 输入方式（二选一）
    sql_group = parser.add_mutually_exclusive_group(required=True)
    sql_group.add_argument('--sql', help='数据源SQL（含 ${WHERE} 占位符）')
    sql_group.add_argument('--sql-file', help='从文件读取SQL（推荐，避免命令行转义问题）')

    parser.add_argument('--table-name', required=True, help='数据源表名')
    parser.add_argument('--pkey', required=True, help='主键字段列表（逗号分隔）')
    parser.add_argument('--widget-name', default='headerGrid',
                        choices=['headerGrid', 'detailsGrid'],
                        help='组件名称 (默认: headerGrid)')
    parser.add_argument('--page-descr-zh', default='主信息', help='中文页面描述 (默认: 主信息)')
    parser.add_argument('--page-descr-en', default='Main Information', help='英文页面描述 (默认: Main Information)')
    parser.add_argument('--page-size', default='100', help='每页行数 (默认: 100)')
    parser.add_argument('--config', help='数据库配置文件路径 (可选)')
    parser.add_argument('--org-id', default='ND', help='组织ID (默认: ND)')
    parser.add_argument('--dry-run', action='store_true', help='仅打印SQL，不执行')
    parser.add_argument('--skip-validation', action='store_true', help='跳过SQL完整性校验（不推荐）')

    args = parser.parse_args()

    # 获取 SQL（从参数或文件）
    sql = args.sql
    if args.sql_file:
        print(f"[信息] 从文件读取 SQL: {args.sql_file}")
        sql = read_sql_from_file(args.sql_file)
        print(f"[信息] SQL 长度: {len(sql)} 字符")
        # 调试输出：显示 SQL 首尾内容
        if DEBUG:
            if len(sql) > 200:
                print(f"[DEBUG] SQL 前100字符: {sql[:100]}")
                print(f"[DEBUG] SQL 后100字符: {sql[-100:]}")
            else:
                print(f"[DEBUG] SQL 内容: {sql}")

    # SQL 完整性校验（除非跳过）
    if not args.skip_validation:
        try:
            validate_sql(sql)
            print("[信息] SQL 完整性校验通过")
        except ValueError as e:
            print(f"\n[错误] SQL 校验失败: {e}", file=sys.stderr)
            print("\n建议：", file=sys.stderr)
            print("  1. 使用 --sql-file 参数从文件读取 SQL（推荐）", file=sys.stderr)
            print("  2. 检查 SQL 是否包含 ${WHERE} 占位符", file=sys.stderr)
            print("  3. 如需跳过校验，使用 --skip-validation 参数（不推荐）", file=sys.stderr)
            sys.exit(1)
    else:
        print("[警告] 已跳过 SQL 完整性校验")

    # 构建 jsonData
    json_data = {
        'pageOrderBy': '',
        'sqlMain': sql,
        'widgetName': args.widget_name,
        'pageSize': args.page_size,
        'generateDataWhenSave': 'Y',
        'text': '单证头' if args.widget_name == 'headerGrid' else '明细信息',
        'pkey': args.pkey,
        'enableEditCell': 'N',
        'isPage': 'Y',
        'tableName': args.table_name,
        'cid': f"c{int(datetime.now().timestamp()) % 100000}"
    }
    json_str = json.dumps(json_data, ensure_ascii=False)

    if args.dry_run:
        print("=== DRY RUN 模式 ===")
        print(f"\njsonData 内容:")
        print(json.dumps(json_data, ensure_ascii=False, indent=2))
        return

    # 加载配置
    try:
        db_config = load_db_config(args.config)
    except Exception as e:
        print(f"错误: 无法加载数据库配置: {e}", file=sys.stderr)
        sys.exit(1)

    user = db_config.get('user', 'UNKNOWN')
    org_id = args.org_id
    func_id = args.function_id
    widget_name = args.widget_name

    # 连接数据库
    try:
        connection = connect_database(db_config)
    except Exception as e:
        print(f"错误: 无法连接数据库: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        cursor = connection.cursor()

        # ──────────────────────────────────────────────
        # 步骤1：实时获取版本号、乐观锁和布局模式
        # ──────────────────────────────────────────────
        print(f"[步骤1] 获取功能 {func_id} 的当前版本号、乐观锁和布局模式...")
        version_info = get_current_version(cursor, org_id, func_id)
        old_version = version_info['currentversion']
        old_opr_seq = version_info['oprseqflag']
        layoutpattern = version_info['layoutpattern']
        new_version = increment_version(old_version)
        new_opr_seq = generate_opr_seq_flag(args.function_id)

        print(f"  当前版本: {old_version} → 新版本: {new_version}")
        print(f"  布局模式: {layoutpattern}（保留原值）")
        print(f"  旧乐观锁: {old_opr_seq[:30]}...")
        print(f"  新乐观锁: {new_opr_seq[:30]}...")

        # ──────────────────────────────────────────────
        # 步骤2：更新 DEV_UDFFUNCFG 版本号（乐观锁）
        # ──────────────────────────────────────────────
        print(f"\n[步骤2] 更新 DEV_UDFFUNCFG 版本号（乐观锁更新）...")
        try:
            affected = update_function_version(
                cursor, org_id, func_id,
                new_version, new_opr_seq, old_opr_seq, user,
                layoutpattern
            )
            if affected == 0:
                # 乐观锁冲突 - 尝试诊断并给出建议
                print("\n  [警告] 乐观锁更新失败（影响 0 行）")
                print("  [诊断] 尝试重新获取最新版本号...")

                # 重新查询最新版本
                cursor.execute("""
                    SELECT currentversion, oprseqflag
                    FROM DEV_UDFFUNCFG
                    WHERE organizationid = :org_id AND functionid = :func_id
                """, {'org_id': org_id, 'func_id': func_id})
                latest = cursor.fetchone()
                if latest:
                    print(f"  [诊断] 数据库当前版本: {latest[0]}, oprseqflag: {latest[1]}")
                    print(f"  [诊断] 我们尝试更新的版本: {new_version}")
                    print(f"  [诊断] 旧的 oprseqflag: {old_opr_seq}")
                    print(f"  [诊断] 新的 oprseqflag: {new_opr_seq}")

                    # 检查是否是同一版本
                    if latest[0] == new_version:
                        print("\n  [诊断] 版本号已匹配目标值，可能是重复执行或上次部分成功")
                        print("  [诊断] 尝试直接更新 oprseqflag...")
                        # 尝试用当前的 oprseqflag 直接更新
                        cursor.execute("""
                            UPDATE DEV_UDFFUNCFG
                            SET oprseqflag = :new_opr_seq,
                                editwho = :edit_who,
                                edittime = SYSDATE
                            WHERE organizationid = :org_id
                              AND functionid = :func_id
                              AND currentversion = :current_ver
                        """, {
                            'new_opr_seq': new_opr_seq,
                            'edit_who': user,
                            'org_id': org_id,
                            'func_id': func_id,
                            'current_ver': latest[0]
                        })
                        if cursor.rowcount > 0:
                            print(f"  [OK] 使用当前版本号更新成功，影响 {cursor.rowcount} 行")
                            affected = cursor.rowcount
                        else:
                            print("  [FAIL] 仍然失败，建议手动检查数据库状态")
                            connection.rollback()
                            sys.exit(1)
                    else:
                        connection.rollback()
                        print("\n  [建议] 数据可能已被其他用户修改，请重新执行此命令。")
                        sys.exit(1)
                else:
                    connection.rollback()
                    print("  [FAIL] 记录不存在！")
                    sys.exit(1)
            else:
                print(f"  [OK] 更新成功，影响 {affected} 行")
        except Exception as e:
            print(f"\n  [错误] 版本更新异常: {e}")
            import traceback
            traceback.print_exc()
            connection.rollback()
            sys.exit(1)

        # ──────────────────────────────────────────────
        # 步骤3：写入 DEV_UDFFUNCFG_QUERY
        # ──────────────────────────────────────────────
        print(f"\n[步骤3] 写入 DEV_UDFFUNCFG_QUERY（数据源SQL配置）...")
        exists = check_query_exists(cursor, org_id, func_id, widget_name)
        if exists:
            rowcount = update_query_config(cursor, org_id, func_id, widget_name,
                                           json_str, new_version, new_opr_seq, user)
            if rowcount == 0:
                connection.rollback()
                raise RuntimeError(
                    f"UPDATE DEV_UDFFUNCFG_QUERY 影响 0 行，"
                    f"functionid={func_id}, widgetname={widget_name}。"
                    f"可能该行不存在或已被其他会话修改。"
                )
            print(f"  [OK] UPDATE 执行成功，影响 {rowcount} 行")
        else:
            rowcount = insert_query_config(cursor, org_id, func_id, widget_name,
                                           json_str, new_version, new_opr_seq, user)
            if rowcount == 0:
                connection.rollback()
                raise RuntimeError(
                    f"INSERT DEV_UDFFUNCFG_QUERY 影响 0 行，"
                    f"functionid={func_id}, widgetname={widget_name}"
                )
            print(f"  [OK] INSERT 执行成功，影响 {rowcount} 行")

        # ──────────────────────────────────────────────
        # 步骤4：写入 BSM_FUNCTION_PAGE + PAGE_ML
        # ──────────────────────────────────────────────
        print(f"\n[步骤4] 写入 BSM_FUNCTION_PAGE（页面注册 + 多语言）...")

        # 4a. 删除旧记录（DELETE 作为事务的一部分）
        delete_function_page(cursor, org_id, func_id)
        print(f"  [OK] 旧记录已清理")

        # 4b. 插入新的页面注册
        page_opr_seq = generate_opr_seq_flag(args.function_id)  # 页面注册用独立的流水号
        insert_function_page(cursor, org_id, func_id,
                             args.table_name, page_opr_seq, user)
        print(f"  [OK] BSM_FUNCTION_PAGE INSERT 成功")

        # 4c. 插入多语言描述（中文 + 英文）
        insert_function_page_ml(cursor, org_id, func_id,
                                args.table_name, args.page_descr_zh,
                                'zh_CN', page_opr_seq, user)
        print(f"  [OK] BSM_FUNCTION_PAGE_ML (zh_CN) INSERT 成功")

        insert_function_page_ml(cursor, org_id, func_id,
                                args.table_name, args.page_descr_en,
                                'en', page_opr_seq, user)
        print(f"  [OK] BSM_FUNCTION_PAGE_ML (en) INSERT 成功")

        # ──────────────────────────────────────────────
        # 提交事务
        # ──────────────────────────────────────────────
        connection.commit()
        print(f"\n[OK] 事务已提交，所有写入完成。")

        # ──────────────────────────────────────────────
        # 验证结果
        # ──────────────────────────────────────────────
        verify_insertion(cursor, org_id, func_id, widget_name, expected_sql=sql)

    except Exception as e:
        connection.rollback()
        print(f"\n错误: {e}", file=sys.stderr)
        print("事务已回滚。", file=sys.stderr)
        sys.exit(1)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
