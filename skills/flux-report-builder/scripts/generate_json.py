#!/usr/bin/env python3
"""
生成报表列配置 JSON

【重要】字段命名规则：
- JSON 中的 field 字段名必须与转换后完整的 SQL 字段名完全一致
- 保留用户定义的别名（AS）
- 去掉表别名前缀（如 A.CUSTOMERID → CUSTOMERID）
- 系统字段（addWho/addTime/editWho/editTime）保持小驼峰格式（从 SQL 中提取，不进行任何转换）

【核心原则】
- 脚本固化：JSON 字段名完全从 SQL 中提取，禁止手动转换大小写
- 大小写保持：SQL 中的字段名是什么格式，JSON 中就是什么格式
- 信任 SQL 转换：SQL 转换步骤（第一部分）已经确保系统字段是小驼峰格式

用法:
    # 从 SQL 文件生成（推荐）
    python generate_json.py --sql-file query.sql --function-id C0104_TEST --output config.json

    # 从表名生成（不推荐，字段名可能不一致）
    python generate_json.py TABLE_NAME C0104_FUNCTION_ID --output config.json
"""

import json
import argparse
import sys
from pathlib import Path

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database, query_table_dictionary, query_column_comments
from sql_parser import parse_sql_fields, parse_table_aliases


# 系统字段列表（需要从用户字段中排除，但保留 addWho/addTime/editWho/editTime）
SYSTEM_FIELDS = {'UDF01', 'UDF02', 'UDF03', 'UDF04', 'UDF05', 'UDF06',
                 'CURRENTVERSION', 'OPRSEQFLAG'}

# 主键/关键字段（添加 batchCopyFlag = "N"）
PRIMARY_KEY_FIELDS = {'ORGANIZATIONID', 'WAREHOUSEID', 'SKU', 'ASNNO', 'ORDERNO'}


def _build_grid_item(field_name: str, udf_label: str, idx: int, field_type: str = "edtxt") -> dict:
    """
    构建单个列配置 item 字典

    Args:
        field_name: 字段名（保持与 SQL 完全一致）
        udf_label: 中文标签
        idx: 序号（从 1 开始）
        field_type: 字段类型，V9->"edtxt", V6->"ro"

    Returns:
        item 字典
    """
    width = "100"
    if len(field_name) > 15 or len(udf_label) > 6:
        width = "150"
    if 'TIME' in field_name.upper() or 'DATE' in field_name.upper():
        width = "135"
    if 'NOTE' in field_name.upper() or 'TEXT' in field_name.upper() or 'DESCR' in field_name.upper():
        width = "180"

    item = {
        "id": 20000 + idx,
        "field": field_name,
        "label": "",
        "udfLabel": udf_label,
        "width": width,
        "sort": "str",
        "align": "left",
        "type": field_type,
        "filterType": "",
        "calTpl": "0000.00",
        "isCal": "N",
        "udfFormat": "",
        "conFormName": "",
        "conFormField": "",
        "connector": "",
        "systemCode": "",
        "udfFlag": "Y",
        "isUdf": "Y",
        "cid": f"c{5000 + idx}",
        "readonly": "Y"
    }

    # 主键/关键字段添加 batchCopyFlag
    if field_name.upper() in PRIMARY_KEY_FIELDS:
        item["batchCopyFlag"] = "N"

    # addWho/editWho 添加 transName（使用小驼峰匹配）
    if field_name in ['addWho', 'editWho']:
        item["transName"] = "USER"
        item["defTransNameFlag"] = "Y"

    return item


def _build_grid_json(items: list, widget_name: str) -> dict:
    """
    构建完整的列配置 JSON（items + gridPro + rightMenu）

    Args:
        items: item 列表
        widget_name: widget 名称

    Returns:
        完整 JSON 配置字典
    """
    grid_pro = [{
        "id": 20000 + len(items) + 1,
        "widgetName": widget_name,
        "freezeField": "",
        "subFunctions": [],
        "mainSubFunctions": [],
        "cid": f"c{5000 + len(items) + 1}"
    }]

    return {
        "items": items,
        "gridPro": grid_pro,
        "rightMenu": []
    }


def _query_field_labels_by_table(cursor, table_aliases: dict, filtered_fields: list, org_id: str = 'ND') -> dict:
    """
    按表分组查询数据字典，获取字段中文标签
    如果数据字典中找不到，则查询数据库表字段注释作为兜底

    Args:
        cursor: 数据库游标
        table_aliases: 表别名映射 {'A': 'DOC_ASN_HEADER', ...}
        filtered_fields: 过滤后的字段信息列表
        org_id: 组织 ID (默认 'ND')

    Returns:
        字段中文标签映射 {'FIELDNAME': '中文名', ...}
    """
    field_labels = {}

    # 按表别名分组字段，减少数据库查询次数
    table_fields_map = {}
    for field_info in filtered_fields:
        table_alias = field_info['table_alias']
        if table_alias:
            if table_alias not in table_fields_map:
                table_fields_map[table_alias] = []
            table_fields_map[table_alias].append(field_info['field_name'])

    # 跟踪哪些字段没有找到标签，用于后续兜底查询
    fields_missing_labels = {}

    # 对每个表别名，查询该表的数据字典
    for table_alias, field_names in table_fields_map.items():
        actual_table_name = table_aliases.get(table_alias.upper())
        if not actual_table_name:
            actual_table_name = table_alias

        try:
            placeholders = ','.join([f':field_{i}' for i in range(len(field_names))])
            params = {f'field_{i}': name.upper() for i, name in enumerate(field_names)}
            params['table_name'] = actual_table_name
            params['org_id'] = org_id

            cursor.execute(f"""
                SELECT H1.FIELDNAME,
                       H1ML.FIELDDESCR,
                       H1ML.UDFFIELDDESCR
                FROM BSM_DATA_DICTIONARY_FIELD H1
                LEFT JOIN BSM_DATA_DICTIONARY_FIELD_ML H1ML
                    ON H1ML.ORGANIZATIONID = H1.ORGANIZATIONID
                    AND H1ML.WAREHOUSEID = H1.WAREHOUSEID
                    AND H1ML.TABLENAME = H1.TABLENAME
                    AND H1ML.FIELDNAME = H1.FIELDNAME
                    AND H1ML.LANGUAGEID = 'zh_CN'
                WHERE H1.ORGANIZATIONID = :org_id
                  AND H1.WAREHOUSEID = '*'
                  AND H1.TABLENAME = :table_name
                  AND UPPER(H1.FIELDNAME) IN ({placeholders})
            """, params)

            found_fields = set()
            for row in cursor.fetchall():
                label = row[2] if row[2] else row[1]
                if label:
                    original_field_name = next(
                        (f for f in field_names if f.upper() == row[0].upper()),
                        row[0]
                    )
                    field_labels[original_field_name] = label
                    found_fields.add(original_field_name.upper())

            # 记录未找到标签的字段，用于后续兜底查询
            missing = [f for f in field_names if f.upper() not in found_fields]
            if missing:
                fields_missing_labels[actual_table_name] = missing

        except Exception as e:
            print(f"警告: 查询表 {actual_table_name} 的数据字典失败: {e}")

    # 兜底：对数据字典中找不到的字段，查询数据库表字段注释
    if fields_missing_labels:
        print("  [兜底] 对未找到数据字典标签的字段，查询数据库字段注释...")
        for table_name, missing_fields in fields_missing_labels.items():
            comments = query_column_comments(cursor, table_name, missing_fields)
            for field_name, comment in comments.items():
                if comment and field_name not in field_labels:
                    field_labels[field_name] = comment
                    print(f"    ✓ 从字段注释获取: {field_name} → {comment}")

    return field_labels


def generate_json_config_from_sql(sql_file: str, function_id: str, widget_name: str = 'headerGrid', output_file: str = None, org_id: str = 'ND', field_type: str = 'edtxt') -> dict:
    """
    从转换后的 SQL 文件生成报表列配置 JSON（推荐方式）

    【重要】此函数从 SQL 中提取字段名，确保 JSON 字段名与 SQL 完全一致
    【优化】识别字段来自哪张表，分别查询每张表的数据字典，使用正确的 TABLENAME 查询条件

    参数:
        sql_file: 转换后的 SQL 文件路径
        function_id: 功能编号
        widget_name: widget 名称 (headerGrid 或 detailsGrid)
        output_file: 输出文件路径（可选）
        org_id: 组织 ID (默认 'ND')
        field_type: 字段类型，V9->"edtxt", V6->"ro" (默认 'edtxt')

    返回:
        JSON 配置字典
    """
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    field_info_list = parse_sql_fields(sql_content)
    table_aliases = parse_table_aliases(sql_content)

    db_config = load_db_config()
    connection = connect_database(db_config)

    try:
        cursor = connection.cursor()

        # 过滤字段（排除系统字段）
        filtered_fields = [
            fi for fi in field_info_list
            if fi['field_name'].upper() not in SYSTEM_FIELDS
        ]

        # 查询数据字典获取中文标签
        field_labels = _query_field_labels_by_table(cursor, table_aliases, filtered_fields, org_id)

        # 生成 items 数组
        items = [
            _build_grid_item(fi['field_name'], field_labels.get(fi['field_name'], fi['field_name']), idx, field_type)
            for idx, fi in enumerate(filtered_fields, start=1)
        ]

        json_config = _build_grid_json(items, widget_name)

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(json_config, f, ensure_ascii=False, indent=2)
            print(f"JSON 配置已保存到: {output_file}")

        return json_config

    finally:
        connection.close()


def generate_json_config(table_name: str, function_id: str, widget_name: str = 'headerGrid', output_file: str = None, org_id: str = 'ND', field_type: str = 'edtxt') -> dict:
    """
    生成报表列配置 JSON（从表名生成，不推荐）

    【警告】此函数从数据字典读取字段名，可能与转换后的 SQL 字段名不一致！
    建议使用 generate_json_config_from_sql() 从 SQL 文件生成。

    参数:
        table_name: 表名
        function_id: 功能编号
        widget_name: widget 名称 (headerGrid 或 detailsGrid)
        output_file: 输出文件路径（可选）
        org_id: 组织 ID (默认 'ND')

    返回:
        JSON 配置字典
    """
    print("【警告】从表名生成 JSON 配置可能导致字段名与 SQL 不一致！")
    print("【建议】使用 generate_json_config_from_sql() 从转换后的 SQL 文件生成。")
    print()

    db_config = load_db_config()
    connection = connect_database(db_config)

    try:
        cursor = connection.cursor()

        # 查询数据字典获取字段中文名称
        fields_info = query_table_dictionary(cursor, table_name, org_id)

        # 构建字段映射
        field_labels = {}
        for field in fields_info:
            label = field['udf_field_descr'] if field['udf_field_descr'] else field['field_descr']
            if label:
                field_labels[field['field_name']] = label

        # 过滤系统字段并生成 items
        items = []
        for idx, field_info in enumerate(fields_info, start=1):
            field_name = field_info['field_name']
            if field_name.upper() in SYSTEM_FIELDS:
                continue

            udf_label = field_labels.get(field_name, field_name)
            items.append(_build_grid_item(field_name, udf_label, idx, field_type))

        json_config = _build_grid_json(items, widget_name)

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(json_config, f, ensure_ascii=False, indent=2)
            print(f"JSON 配置已保存到: {output_file}")

        return json_config

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description='生成报表列配置 JSON')
    parser.add_argument('table_name', nargs='?', help='表名（不推荐，建议使用 --sql-file）')
    parser.add_argument('function_id', nargs='?', help='功能编号')
    parser.add_argument('--sql-file', help='转换后的 SQL 文件路径（推荐，确保字段名一致）')
    parser.add_argument('--function-id', dest='function_id_option', help='功能编号（可选，优先级高于位置参数）')
    parser.add_argument('--widget-name', choices=['headerGrid', 'detailsGrid'],
                       default='headerGrid', help='widget 名称 (默认: headerGrid)')
    parser.add_argument('--type', choices=['edtxt', 'ro'],
                       default='edtxt', help='字段类型，V9 用 edtxt，V6 用 ro (默认: edtxt)')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--org-id', default='ND', help='组织 ID (默认: ND)')

    args = parser.parse_args()

    # 优先使用 --function-id 选项，否则使用位置参数
    function_id = args.function_id_option or args.function_id

    try:
        if args.sql_file:
            json_config = generate_json_config_from_sql(
                args.sql_file,
                function_id,
                args.widget_name,
                args.output,
                args.org_id,
                args.type
            )
        elif args.table_name and function_id:
            json_config = generate_json_config(
                args.table_name,
                function_id,
                args.widget_name,
                args.output,
                args.org_id,
                args.type
            )
        else:
            print("错误：必须指定 --sql-file 参数或同时指定 table_name 和 function_id")
            sys.exit(1)

        if not args.output:
            print(json.dumps(json_config, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
