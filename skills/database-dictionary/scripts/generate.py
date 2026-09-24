# -*- coding: utf-8 -*-
"""
数据库字典生成脚本
从 BSM_DATA_DICTIONARY_FIELD 或 COMMENT ON 生成数据库字典
"""
import os
import subprocess

def get_db_config():
    """从项目根目录 .env 读取数据库配置（DB_CONNECTION）"""
    current_dir = os.getcwd()
    for _ in range(10):
        env_path = os.path.join(current_dir, '.env')
        if os.path.exists(env_path):
            conn_str = ''
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('DB_CONNECTION='):
                        conn_str = line.split('=', 1)[1].strip()
                        break
            if not conn_str:
                raise Exception(".env 中未找到 DB_CONNECTION")
            # 解析连接字符串: USER/PASSWORD@HOST:PORT/SERVICE
            user_pass, host_part = conn_str.rsplit('@', 1)
            user, password = user_pass.split('/', 1)
            return {
                'conn_str': conn_str,
                'user': user,
                'password': password,
                'database': host_part,
                'project_dir': current_dir
            }
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent

    raise Exception("未找到 .env 配置文件")

def get_output_dir(project_dir):
    """获取输出目录"""
    return os.path.join(project_dir, 'docs', 'dictionaries', 'tables')

def get_index_path(project_dir):
    """获取索引文件路径"""
    return os.path.join(project_dir, 'docs', 'dictionaries', '00_表索引.md')

def run_sql_script(conn_str, sql_script, spool_file=None):
    """运行 SQL 脚本文件"""
    cmd = f'sql -S "{conn_str}" << \'EOF\'\n{sql_script}\nEOF'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if spool_file and os.path.exists(spool_file):
        with open(spool_file, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    return result.stdout

def export_bsm_dict(conn_str, output_file):
    """导出 BSM_DATA_DICTIONARY_FIELD 数据"""
    sql = f"""SET LINESIZE 500
SET PAGESIZE 1000
SET FEEDBACK OFF
SET HEADING OFF

SPOOL {output_file}

SELECT TM.TABLENAME || '|' ||
    NVL(TM.TABLEDESCR, ' ') || '|' ||
    F.FIELDNAME || '|' ||
    NVL(FM.FIELDDESCR, ' ') || '|' ||
    NVL(FM.UDFFIELDDESCR, ' ') || '|' ||
    NVL(FM.NOTETEXT, ' ') || '|' ||
    F.KEYFLAG || '|' ||
    F.FIELDTYPE || '|' ||
    F.NULLFLAG || '|' ||
    NVL(F.DEFAULTVALUE, ' ')
FROM BSM_DATA_DICTIONARY_FIELD F
LEFT JOIN BSM_DATA_DICTIONARY_TABLE_ML TM ON TM.ORGANIZATIONID=F.ORGANIZATIONID
    AND TM.WAREHOUSEID=F.WAREHOUSEID AND TM.TABLENAME=F.TABLENAME
    AND TM.LANGUAGEID='zh_CN'
LEFT JOIN BSM_DATA_DICTIONARY_FIELD_ML FM ON FM.ORGANIZATIONID=F.ORGANIZATIONID
    AND FM.WAREHOUSEID=F.WAREHOUSEID AND FM.TABLENAME=F.TABLENAME
    AND FM.FIELDNAME=F.FIELDNAME AND FM.LANGUAGEID='zh_CN'
WHERE F.ORGANIZATIONID='DONGCHENG' AND F.WAREHOUSEID='*'
ORDER BY TM.TABLENAME, F.SHOWSEQUENCE;

SPOOL OFF
EXIT
"""
    subprocess.run(f'sql -S "{conn_str}" << \'EOF\'\n{sql}\nEOF', shell=True, capture_output=True, encoding='utf-8', errors='replace')

def export_comment_dict(conn_str, output_file):
    """导出 COMMENT ON 数据（使用 PL/SQL 处理 LONG 类型）"""
    sql = """SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 500
SET FEEDBACK OFF

SPOOL """ + output_file + """

DECLARE
    CURSOR t IS
        SELECT t.table_name, t.comments AS table_desc
        FROM user_tab_comments t
        WHERE t.table_name NOT IN (
            SELECT DISTINCT f.TABLENAME
            FROM BSM_DATA_DICTIONARY_FIELD f
            WHERE f.ORGANIZATIONID = 'DONGCHENG' AND f.WAREHOUSEID = '*'
        )
        AND t.table_name NOT LIKE 'BIN$%'
        AND t.table_name NOT LIKE 'DR$%'
        AND t.table_type = 'TABLE'
        AND t.comments IS NOT NULL
        ORDER BY t.table_name;

    CURSOR col_c(p_table_name VARCHAR2) IS
        SELECT col.column_name, col.data_type, col.nullable, cc.comments AS col_desc
        FROM user_tab_columns col
        LEFT JOIN user_col_comments cc ON col.table_name = cc.table_name AND col.column_name = cc.column_name
        WHERE col.table_name = p_table_name
        ORDER BY col.column_id;
BEGIN
    FOR t_rec IN t LOOP
        DBMS_OUTPUT.PUT_LINE('===START===');
        DBMS_OUTPUT.PUT_LINE('TABLE:' || t_rec.table_name || '|' || t_rec.table_desc);

        FOR col_rec IN col_c(t_rec.table_name) LOOP
            DBMS_OUTPUT.PUT_LINE(col_rec.column_name || '|' || col_rec.data_type || '|' || col_rec.nullable || '|' || NVL(col_rec.col_desc, ''));
        END LOOP;
    END LOOP;
END;
/

SPOOL OFF
EXIT
"""
    subprocess.run(f'sql -S "{conn_str}" << \'EOF\'\n{sql}\nEOF', shell=True, capture_output=True, encoding='utf-8', errors='replace')

def generate_bsm_markdown(input_file, output_dir):
    """生成 BSM 字典的 Markdown 文件"""
    tables = {}
    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or 'Picked up' in line:
                continue
            parts = line.split('|')
            if len(parts) >= 10:
                table_name = parts[0].strip()
                table_desc = parts[1].strip()
                field_name = parts[2].strip()
                field_desc = parts[3].strip()
                udf_desc = parts[4].strip()
                note_text = parts[5].strip()
                key_flag = parts[6].strip()
                field_type = parts[7].strip()
                null_flag = parts[8].strip()
                default_val = parts[9].strip()

                if not table_name or not field_name:
                    continue

                if table_name not in tables:
                    tables[table_name] = {'description': table_desc, 'fields': []}

                tables[table_name]['fields'].append({
                    'name': field_name,
                    'desc': field_desc,
                    'udf_desc': udf_desc,
                    'note': note_text,
                    'key_flag': key_flag,
                    'type': field_type,
                    'null_flag': null_flag,
                    'default': default_val
                })

    # 生成 Markdown 文件
    for table_name, table_data in tables.items():
        fields = table_data['fields']
        table_desc = table_data['description']

        md = f"# {table_name}\n\n**表描述**: {table_desc}\n\n## 字段列表\n\n"
        md += "| 字段名称 | 字段描述 | 自定义描述 | 备注 | 主键标记 | 字段类型 | 允许为空 | 默认值 |\n"
        md += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"

        for field in fields:
            key = 'Y' if field['key_flag'].upper() == 'Y' else 'N'
            null = 'Y' if field['null_flag'].upper() == 'Y' else 'N'
            md += f"| {field['name']} | {field['desc']} | {field['udf_desc']} | {field['note']} | {key} | {field['type']} | {null} | {field['default']} |\n"

        # 清理表名中的非法字符
        clean_name = table_name.strip()
        for char in '<>:"/\\|?*':
            clean_name = clean_name.replace(char, '_')

        with open(os.path.join(output_dir, f"{clean_name}.md"), 'w', encoding='utf-8') as f:
            f.write(md)

    print(f"BSM 字典: 生成 {len(tables)} 个文件")
    return tables

def generate_comment_markdown(input_file, output_dir):
    """生成 COMMENT 字典的 Markdown 文件"""
    tables = {}
    current_table = None
    current_desc = None
    fields = []

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()

            if line.startswith('===START==='):
                if current_table and fields:
                    tables[current_table] = {'description': current_desc, 'fields': fields}
                current_table = None
                current_desc = None
                fields = []

            elif line.startswith('TABLE:'):
                parts = line[6:].split('|')
                current_table = parts[0]
                current_desc = parts[1] if len(parts) > 1 else ''

            elif line and '|' in line and not line.startswith('Picked up'):
                parts = line.split('|')
                if len(parts) >= 4:
                    fields.append({
                        'name': parts[0],
                        'type': parts[1],
                        'nullable': parts[2],
                        'desc': parts[3] if len(parts) > 3 else ''
                    })

    if current_table and fields:
        tables[current_table] = {'description': current_desc, 'fields': fields}

    # 生成 Markdown 文件
    for table_name, table_data in tables.items():
        fields = table_data['fields']
        table_desc = table_data['description']

        md = f"# {table_name}\n\n**表描述**: {table_desc}\n\n## 字段列表（来自 COMMENT ON）\n\n"
        md += "| 字段名称 | 字段描述 | 字段类型 | 允许为空 |\n"
        md += "| :--- | :--- | :--- | :--- |\n"

        for field in fields:
            null = 'Y' if field['nullable'].upper() == 'Y' else 'N'
            md += f"| {field['name']} | {field['desc']} | {field['type']} | {null} |\n"

        with open(os.path.join(output_dir, f"{table_name}.md"), 'w', encoding='utf-8') as f:
            f.write(md)

    print(f"COMMENT 字典: 生成 {len(tables)} 个文件")
    return tables

def generate_index(output_dir, index_path):
    """生成索引文件"""
    tables = []
    for f in os.listdir(output_dir):
        if f.endswith('.md'):
            tables.append(f[:-3])

    tables.sort()

    index_md = f"# 数据库字典表索引\n\n共 {len(tables)} 张表\n\n"
    index_md += "| 表名 | 表描述 |\n| :--- | :--- |\n"

    for table_name in tables:
        file_path = os.path.join(output_dir, f"{table_name}.md")
        table_desc = ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('**表描述**:'):
                        table_desc = line.replace('**表描述**:', '').strip()
                        break
        except:
            pass
        index_md += f"| [{table_name}](tables/{table_name}.md) | {table_desc} |\n"

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_md)

    print(f"索引文件已更新: {len(tables)} 张表")

def main():
    """主函数"""
    # 获取配置
    config = get_db_config()
    conn_str = config['conn_str']
    output_dir = get_output_dir(config['project_dir'])
    index_path = get_index_path(config['project_dir'])
    project_dir = config['project_dir']

    print(f"项目目录: {project_dir}")
    print(f"输出目录: {output_dir}")
    print(f"数据库: {config['database']}")

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)

    # 临时文件
    bsm_file = os.path.join(project_dir, 'bsm_dict_export.txt')
    comment_file = os.path.join(project_dir, 'comment_dict_export.txt')

    # 导出数据
    print("\n[1/4] 导出 BSM_DATA_DICTIONARY_FIELD 字典...")
    export_bsm_dict(conn_str, bsm_file)

    print("[2/4] 导出 COMMENT ON 字典...")
    export_comment_dict(conn_str, comment_file)

    # 生成 Markdown
    print("\n[3/4] 生成 Markdown 文件...")
    generate_bsm_markdown(bsm_file, output_dir)
    generate_comment_markdown(comment_file, output_dir)

    # 生成索引
    print("\n[4/4] 生成索引文件...")
    generate_index(output_dir, index_path)

    # 清理临时文件
    for f in [bsm_file, comment_file]:
        if os.path.exists(f):
            os.remove(f)

    print("\n完成!")

if __name__ == '__main__':
    main()
