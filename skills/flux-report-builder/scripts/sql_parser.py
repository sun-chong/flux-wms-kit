#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL 解析公共模块

提供从 SQL 语句中提取字段列表和表别名映射的功能。
被 generate_json.py 和 generate_form_json.py 共同使用。
"""

import re


def parse_sql_fields(sql_content: str) -> list:
    """
    从 SQL 中提取字段列表（保持原始顺序和大小写）

    Args:
        sql_content: SQL 语句

    Returns:
        字段信息列表，每个元素是字典：
        {
            'field_name': '字段名（保留别名）',
            'table_alias': '表别名（如 A、B）或 None'
        }
    """
    # 移除注释
    sql_content = re.sub(r'--.*$', '', sql_content, flags=re.MULTILINE)
    sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.DOTALL)

    # 提取 SELECT 和 FROM 之间的内容
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_content, re.IGNORECASE | re.DOTALL)
    if not select_match:
        raise ValueError("无法解析 SQL：未找到 SELECT 子句")

    select_clause = select_match.group(1)

    # 分割字段（处理嵌套括号和函数）
    fields = []
    current_field = ""
    paren_depth = 0

    for char in select_clause:
        if char == '(':
            paren_depth += 1
            current_field += char
        elif char == ')':
            paren_depth -= 1
            current_field += char
        elif char == ',' and paren_depth == 0:
            fields.append(current_field.strip())
            current_field = ""
        else:
            current_field += char

    if current_field.strip():
        fields.append(current_field.strip())

    # 提取字段名（处理别名和函数）
    field_info_list = []
    for field in fields:
        field_info = {'field_name': None, 'table_alias': None}

        # 处理 DBMS_LOB.SUBSTR 函数（特殊处理 noteText）
        if 'DBMS_LOB.SUBSTR' in field.upper():
            # 如果有 AS 别名，提取别名
            as_match = re.search(r'\s+AS\s+(\w+)', field, re.IGNORECASE)
            if as_match:
                field_info['field_name'] = as_match.group(1)
                # 提取表别名
                lob_match = re.search(r'DBMS_LOB\.SUBSTR\(\s*(\w+)\.', field, re.IGNORECASE)
                if lob_match:
                    field_info['table_alias'] = lob_match.group(1)
                field_info_list.append(field_info)
                continue

            # 否则，提取函数中的字段名（如 noteText）
            lob_match = re.search(r'DBMS_LOB\.SUBSTR\(\s*(\w+)\.(\w+)', field, re.IGNORECASE)
            if lob_match:
                field_info['table_alias'] = lob_match.group(1)
                field_info['field_name'] = lob_match.group(2)
                field_info_list.append(field_info)
                continue

            # 如果都无法匹配，跳过
            continue

        # 处理 AS 别名
        as_match = re.search(r'\s+AS\s+(\w+)', field, re.IGNORECASE)
        if as_match:
            field_info['field_name'] = as_match.group(1)
            # 提取表别名（AS 前面的部分）
            if '.' in field:
                field_info['table_alias'] = field.split('.')[0]
            field_info_list.append(field_info)
            continue

        # 处理表别名前缀（如 UBC.ORGANIZATIONID）
        if '.' in field:
            parts = field.split('.')
            field_info['table_alias'] = parts[0]
            field = parts[-1]

        # 处理没有 AS 的别名（如 "WAREHOUSEID WA"）
        alias_match = re.match(r'^(\w+)\s+(\w+)$', field)
        if alias_match:
            field_info['field_name'] = alias_match.group(2)
            field_info_list.append(field_info)
            continue

        # 只保留有效的字段名
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', field):
            field_info['field_name'] = field
            field_info_list.append(field_info)

    return field_info_list


def parse_table_aliases(sql_content: str) -> dict:
    """
    从 SQL 中解析表别名映射

    Args:
        sql_content: SQL 语句

    Returns:
        字典，键是表别名，值是实际表名
        例如：{'A': 'DOC_ASN_HEADER', 'B': 'DOC_ASN_DETAIL'}
    """
    # 移除注释
    sql_content = re.sub(r'--.*$', '', sql_content, flags=re.MULTILINE)
    sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.DOTALL)

    table_aliases = {}

    # 提取 FROM 子句
    from_match = re.search(r'FROM\s+(.*?)(?:\s+WHERE|\s+GROUP|\s+ORDER|\s+LEFT|\s+RIGHT|\s+INNER|\s+JOIN|$)',
                          sql_content, re.IGNORECASE | re.DOTALL)
    if not from_match:
        return table_aliases

    from_clause = from_match.group(1)

    # 先提取主表（FROM 后面的第一个表）
    # 格式：TABLE_NAME ALIAS 或 TABLE_NAME AS ALIAS
    main_table_match = re.match(r'(\w+)(?:\s+(?:AS\s+)?(\w+))?', from_clause, re.IGNORECASE)
    if main_table_match:
        table_name = main_table_match.group(1)
        alias = main_table_match.group(2) or table_name  # 如果没有别名，使用表名作为别名
        table_aliases[alias.upper()] = table_name

    # 提取 JOIN 的表
    # 格式：JOIN TABLE_NAME ALIAS ON 或 JOIN TABLE_NAME AS ALIAS ON
    join_pattern = r'JOIN\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?\s+ON'
    for match in re.finditer(join_pattern, sql_content, re.IGNORECASE):
        table_name = match.group(1)
        alias = match.group(2) or table_name  # 如果没有别名，使用表名作为别名
        table_aliases[alias.upper()] = table_name

    return table_aliases
