#!/usr/bin/env python3
"""
FLUX WMS 表单配置写入工具
将表单配置 JSON 写入 DEV_UDFFUNCFG_FORM 表，同时更新版本号和多语言标签
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database


def generate_oprseqflag():
    """生成操作流水标记"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{timestamp}0000000001RA010"


def query_multilang_config(cursor, function_cid: str, widget_name: str = 'headerGrid',
                          org_id: str = 'ND'):
    """步骤 1: 查询多语言配置"""
    print("\n[步骤1] 查询已有多语言标签配置...")

    # 根据 widget_name 确定 form_name 前缀
    if widget_name == 'detailsGrid':
        form_name_prefix = 'detailsGridFormEditorForm'
    else:
        form_name_prefix = 'headerGridFormEditorForm'

    cursor.execute("""
        SELECT PROPKEYID, PROPKEYVALUE
        FROM BSM_MULTILANG_TEXT_ML
        WHERE ORGANIZATIONID = :org_id
          AND WAREHOUSEID = '*'
          AND PROPKEYID LIKE :prefix || '_%'
          AND LANGUAGEID = 'zh_CN'
    """, {'org_id': org_id, 'prefix': form_name_prefix})

    results = cursor.fetchall()
    print(f"  [OK] 找到 {len(results)} 个多语言标签记录")
    return results


def verify_permission(cursor, user_id: str, function_cid: str):
    """步骤 2: 权限验证"""
    print("\n[步骤2] 验证用户编辑权限...")

    cursor.execute("""
        SELECT COUNT(*) as hasAuth
        FROM BSM_USER_CUSAUTHORIZATION
        WHERE userid = :user_id
          AND functionid = :function_cid
          AND activeflag = 'Y'
    """, {'user_id': user_id, 'function_cid': function_cid})

    result = cursor.fetchone()
    has_auth = result[0] > 0

    if not has_auth:
        print("  [FAIL] 权限验证失败：用户无编辑权限")
        return False

    print("  [OK] 权限验证通过")
    return True


def query_dictionary(cursor, org_id: str):
    """步骤 3: 查询数据字典"""
    print("\n[步骤3] 查询数据字典获取表结构元数据...")

    # 查询 DEV_UDFFUNCFG 表字段定义
    cursor.execute("""
        SELECT fieldName, fieldType, nullflag, defaultValue
        FROM BSM_DATA_DICTIONARY_FIELD
        WHERE organizationId = :org_id
          AND warehouseId = '*'
          AND tableName = 'DEV_UDFFUNCFG'
    """, {'org_id': org_id})
    dev_udffunfg_fields = cursor.fetchall()

    # 查询 BSM_FUNCTION_ML 表字段定义
    cursor.execute("""
        SELECT fieldName, fieldType, nullflag, defaultValue
        FROM BSM_DATA_DICTIONARY_FIELD
        WHERE organizationId = :org_id
          AND warehouseId = '*'
          AND tableName = 'BSM_FUNCTION_ML'
    """, {'org_id': org_id})
    bsm_function_ml_fields = cursor.fetchall()

    # 查询 DEV_UDFFUNCFG_ML 表字段定义
    cursor.execute("""
        SELECT fieldName, fieldType, nullflag, defaultValue
        FROM BSM_DATA_DICTIONARY_FIELD
        WHERE organizationId = :org_id
          AND warehouseId = '*'
          AND tableName = 'DEV_UDFFUNCFG_ML'
    """, {'org_id': org_id})
    dev_udffunfg_ml_fields = cursor.fetchall()

    print(f"  [OK] DEV_UDFFUNCFG 表字段数: {len(dev_udffunfg_fields)}")
    print(f"  [OK] BSM_FUNCTION_ML 表字段数: {len(bsm_function_ml_fields)}")
    print(f"  [OK] DEV_UDFFUNCFG_ML 表字段数: {len(dev_udffunfg_ml_fields)}")

    return {
        'dev_udffunfg': dev_udffunfg_fields,
        'bsm_function_ml': bsm_function_ml_fields,
        'dev_udffunfg_ml': dev_udffunfg_ml_fields
    }


def update_version(cursor, function_cid: str, user_id: str):
    """步骤 4: 更新版本号（乐观锁）"""
    print("\n[步骤4] 更新版本号...")

    # 查询当前版本信息
    cursor.execute("""
        SELECT currentversion, oprseqflag
        FROM DEV_UDFFUNCFG
        WHERE functionid = :function_cid
    """, {'function_cid': function_cid})

    result = cursor.fetchone()
    if not result:
        print("  [FAIL] 未找到功能配置记录")
        return None, None

    current_version = result[0]
    current_oprseqflag = result[1]

    # 计算新版本号
    new_version = int(current_version) + 1
    new_oprseqflag = generate_oprseqflag()

    # 使用乐观锁更新版本号
    cursor.execute("""
        UPDATE DEV_UDFFUNCFG
        SET currentversion = :new_version,
            editwho = :user_id,
            edittime = SYSDATE,
            oprseqflag = :new_oprseqflag
        WHERE functionid = :function_cid
          AND oprseqflag = :current_oprseqflag
    """, {
        'new_version': new_version,
        'user_id': user_id,
        'new_oprseqflag': new_oprseqflag,
        'function_cid': function_cid,
        'current_oprseqflag': current_oprseqflag
    })

    # 检查乐观锁是否成功
    if cursor.rowcount == 0:
        print("  [FAIL] 乐观锁冲突：数据已被其他用户修改")
        return None, None

    print(f"  [OK] 版本号更新成功: {current_version} -> {new_version}")
    print(f"  [OK] 新操作流水标记: {new_oprseqflag}")

    return new_version, new_oprseqflag


def insert_form_config(cursor, form_cid: str, func_code: str, form_json_config: dict,
                       org_id: str, user_id: str, oprseqflag: str):
    """步骤 6: 插入 Form 配置"""
    print("\n[步骤5] 插入表单配置...")

    form_json_str = json.dumps(form_json_config, ensure_ascii=False, indent=2)

    cursor.execute("""
        INSERT INTO DEV_UDFFUNCFG_FORM (
            formname,
            functionid,
            jsondata,
            organizationid,
            addwho,
            addtime,
            editwho,
            edittime,
            currentversion,
            oprseqflag
        ) VALUES (
            :formname,
            :functionid,
            :jsondata,
            :organizationid,
            :addwho,
            SYSDATE,
            :editwho,
            SYSDATE,
            1,
            :oprseqflag
        )
    """, {
        'formname': form_cid,
        'functionid': func_code,
        'jsondata': form_json_str,
        'organizationid': org_id,
        'addwho': user_id,
        'editwho': user_id,
        'oprseqflag': oprseqflag
    })

    print(f"  [OK] 表单配置插入成功: CID={form_cid}, FUNCCODE={func_code}")


def maintain_multilang(cursor, form_json_config: dict, widget_name: str,
                      org_id: str, user_id: str, func_code: str):
    """步骤 7: 维护多语言标签"""
    print("\n[步骤6] 维护多语言标签...")

    # 从 JSON 配置中提取字段标签
    # 表单 JSON 结构：items = [settings, block{list:[field1,...]}, block{list:[...]}, block{list:[...]}]
    # 需要进入 block 的 list 子数组遍历实际字段
    items = form_json_config.get('items', [])
    label_count = 0

    # 收集所有需要处理的字段（从嵌套结构中提取）
    all_fields = []
    for item in items:
        if item.get('type') == 'block':
            for field in item.get('list', []):
                if field.get('type') in ['input', 'combo', 'checkbox', 'hidden']:
                    all_fields.append(field)
            # fieldset 内也可能嵌套字段
            for field in item.get('list', []):
                if field.get('type') == 'fieldset':
                    for sub_field in field.get('list', []):
                        if sub_field.get('type') in ['input', 'combo', 'checkbox']:
                            all_fields.append(sub_field)

    for field_item in all_fields:
        field_name = field_item.get('name', '')
        udf_label = field_item.get('udfLabel', '')

        if not field_name or not udf_label:
            continue

        # 构建 textKey
        text_key = f"{widget_name}FormEditorForm_{field_name}"

        # 检查 BSM_MULTILANG_TEXT 是否已存在
        cursor.execute("""
            SELECT textGid FROM BSM_MULTILANG_TEXT
            WHERE ORGANIZATIONID = :org_id
              AND WAREHOUSEID = '*'
              AND TEXTKEY = :text_key
        """, {'org_id': org_id, 'text_key': text_key})

        result = cursor.fetchone()

        if result:
            # 已存在，获取 textGid
            text_gid = result[0]

            # 更新现有记录
            cursor.execute("""
                UPDATE BSM_MULTILANG_TEXT
                SET TEXTVALUE = :text_value,
                    EDITWHO = :user_id,
                    EDITTIME = SYSDATE
                WHERE textGid = :text_gid
            """, {'text_value': udf_label, 'user_id': user_id, 'text_gid': text_gid})
        else:
            # 不存在，插入新记录
            text_gid = f"TG{datetime.now().strftime('%Y%m%d%H%M%S')}{label_count:04d}"

            cursor.execute("""
                INSERT INTO BSM_MULTILANG_TEXT (
                    TEXTGID, MODULEID, TEXTTYPE, TEXTKEY, TEXTVALUE,
                    ORGANIZATIONID, WAREHOUSEID, ADDWHO, EDITWHO, ADDTIME, EDITTIME
                ) VALUES (
                    :text_gid, 'UDFFUNCFG', 'DEV_UDFFUNCFG', :text_key, :text_value,
                    :org_id, '*', :user_id, :user_id, SYSDATE, SYSDATE
                )
            """, {
                'text_gid': text_gid,
                'text_key': text_key,
                'text_value': udf_label,
                'org_id': org_id,
                'user_id': user_id
            })

        # 写入中文标签 (zh_CN)
        cursor.execute("""
            SELECT COUNT(*) FROM BSM_MULTILANG_TEXT_ML
            WHERE textGid = :text_gid AND LANGUAGEID = 'zh_CN'
        """, {'text_gid': text_gid})

        if cursor.fetchone()[0] > 0:
            # 已存在，更新
            cursor.execute("""
                UPDATE BSM_MULTILANG_TEXT_ML
                SET TEXTVALUE = :text_value,
                    EDITWHO = :user_id,
                    EDITTIME = SYSDATE
                WHERE textGid = :text_gid AND LANGUAGEID = 'zh_CN'
            """, {'text_value': udf_label, 'user_id': user_id, 'text_gid': text_gid})
        else:
            # 不存在，插入
            cursor.execute("""
                INSERT INTO BSM_MULTILANG_TEXT_ML (
                    TEXTGID, LANGUAGEID, TEXTVALUE,
                    ORGANIZATIONID, WAREHOUSEID, ADDWHO, EDITWHO, ADDTIME, EDITTIME
                ) VALUES (
                    :text_gid, 'zh_CN', :text_value,
                    :org_id, '*', :user_id, :user_id, SYSDATE, SYSDATE
                )
            """, {'text_gid': text_gid, 'text_value': udf_label, 'org_id': org_id, 'user_id': user_id})

        # 写入英文标签 (en)
        cursor.execute("""
            SELECT COUNT(*) FROM BSM_MULTILANG_TEXT_ML
            WHERE textGid = :text_gid AND LANGUAGEID = 'en'
        """, {'text_gid': text_gid})

        if cursor.fetchone()[0] > 0:
            # 已存在，更新
            cursor.execute("""
                UPDATE BSM_MULTILANG_TEXT_ML
                SET TEXTVALUE = :text_value,
                    EDITWHO = :user_id,
                    EDITTIME = SYSDATE
                WHERE textGid = :text_gid AND LANGUAGEID = 'en'
            """, {'text_value': field_name, 'user_id': user_id, 'text_gid': text_gid})
        else:
            # 不存在，插入（英文标签使用字段名）
            cursor.execute("""
                INSERT INTO BSM_MULTILANG_TEXT_ML (
                    TEXTGID, LANGUAGEID, TEXTVALUE,
                    ORGANIZATIONID, WAREHOUSEID, ADDWHO, EDITWHO, ADDTIME, EDITTIME
                ) VALUES (
                    :text_gid, 'en', :text_value,
                    :org_id, '*', :user_id, :user_id, SYSDATE, SYSDATE
                )
            """, {'text_gid': text_gid, 'text_value': field_name, 'org_id': org_id, 'user_id': user_id})

        label_count += 1

    print(f"  [OK] 已写入 {label_count} 个多语言标签")


def verify_insertion(cursor, func_code: str):
    """验证插入结果"""
    print("\n" + "=" * 60)
    print("写入验证报告")
    print("=" * 60)

    # 修复：使用正确的字段名 JSONDATA 和 FUNCTIONID
    # 验证表单配置
    cursor.execute("""
        SELECT CID, FUNCTIONID, LENGTH(JSONDATA) AS JSON_LENGTH
        FROM DEV_UDFFUNCFG_FORM
        WHERE FUNCTIONID = :func_code
    """, {'func_code': func_code})

    result = cursor.fetchone()
    if result:
        print(f"\n1. DEV_UDFFUNCFG_FORM（表单配置）:")
        print(f"   CID: {result[0]}")
        print(f"   功能编号: {result[1]}")
        print(f"   JSON 长度: {result[2]} 字节")

        # 验证第一个字段的中文标签
        cursor.execute("""
            SELECT JSON_VALUE(JSONDATA, '$.items[1].udfLabel')
            FROM DEV_UDFFUNCFG_FORM
            WHERE FUNCTIONID = :func_code
        """, {'func_code': func_code})

        label_result = cursor.fetchone()
        if label_result and label_result[0]:
            print(f"   第一个字段的 udfLabel: {label_result[0]}")

    # 验证多语言标签
    cursor.execute("""
        SELECT COUNT(*)
        FROM BSM_MULTILANG_TEXT_ML
        WHERE PROPKEYID LIKE '%FormEditorForm_%'
          AND LANGUAGEID = 'zh_CN'
    """)

    count = cursor.fetchone()[0]
    print(f"\n2. 多语言标签:")
    print(f"   BSM_MULTILANG_TEXT_ML (zh_CN) 记录数: {count}")

    # 显示示例标签
    cursor.execute("""
        SELECT PROPKEYID, PROPVALUE
        FROM BSM_MULTILANG_TEXT_ML
        WHERE PROPKEYID LIKE '%FormEditorForm_%'
          AND LANGUAGEID = 'zh_CN'
          AND ROWNUM <= 3
    """)

    samples = cursor.fetchall()
    if samples:
        print(f"   示例标签:")
        for sample in samples:
            print(f"     - {sample[0]}: {sample[1]}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='FLUX WMS 表单配置写入工具')
    parser.add_argument('function_cid', help='功能 CID (如 C0104_UDF_PURCHASINGGROUP)')
    parser.add_argument('form_cid', help='表单配置 CID (如 C0104_AUDF_PURCHASINGGROUPeditRegionForm)')
    parser.add_argument('form_json_file', help='表单配置 JSON 文件路径')
    parser.add_argument('--widget-name', default='headerGrid',
                       choices=['headerGrid', 'detailsGrid'],
                       help='组件名称 (默认: headerGrid)')
    parser.add_argument('--org-id', default='ND', help='组织 ID (默认: ND)')
    parser.add_argument('--config', help='数据库配置文件路径 (可选)')

    args = parser.parse_args()

    # 检查 JSON 文件是否存在
    json_path = Path(args.form_json_file)
    if not json_path.exists():
        print(f"错误: JSON 文件不存在: {args.form_json_file}")
        sys.exit(1)

    # 加载 JSON 数据
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            form_json_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 文件格式错误: {e}")
        sys.exit(1)

    # 加载数据库配置
    try:
        db_config = load_db_config(args.config)
    except Exception as e:
        print(f"错误: 无法加载数据库配置: {e}")
        sys.exit(1)

    # 从配置文件获取用户信息
    user_id = db_config.get('user', 'UNKNOWN')
    print(f"操作用户: {user_id}")
    print(f"功能 CID: {args.function_cid}")
    print(f"表单 CID: {args.form_cid}")
    print(f"组件名称: {args.widget_name}")
    print(f"组织 ID: {args.org_id}")

    # 连接数据库
    try:
        connection = connect_database(db_config)
    except Exception as e:
        print(f"错误: 无法连接数据库: {e}")
        sys.exit(1)

    try:
        cursor = connection.cursor()

        # 步骤 1: 查询多语言配置
        query_multilang_config(cursor, args.function_cid, args.widget_name, args.org_id)

        # 步骤 2: 权限验证
        if not verify_permission(cursor, user_id, args.function_cid):
            print("\n错误: 用户无编辑权限")
            sys.exit(1)

        # 步骤 3: 查询数据字典
        query_dictionary(cursor, args.org_id)

        # 步骤 4: 更新版本号
        new_version, new_oprseqflag = update_version(cursor, args.function_cid, user_id)
        if new_version is None:
            print("\n错误: 版本号更新失败（乐观锁冲突）")
            sys.exit(1)

        # 步骤 5: 插入表单配置
        insert_form_config(
            cursor, args.form_cid, args.function_cid,
            form_json_config, args.org_id, user_id, new_oprseqflag
        )

        # 步骤 6: 维护多语言标签
        maintain_multilang(
            cursor, form_json_config, args.widget_name,
            args.org_id, user_id, args.function_cid
        )

        # 提交事务
        connection.commit()
        print("\n[OK] 事务已提交，所有写入完成。")

        # 验证结果
        verify_insertion(cursor, args.function_cid)

    except Exception as e:
        connection.rollback()
        print(f"\n[ERROR] {e}")
        print("事务已回滚")
        sys.exit(1)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
