#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLUX WMS 表单 JSON 配置生成脚本

【重要】字段命名规则：
- JSON 中的字段名（name 字段）必须与转换后完整的 SQL 字段名完全一致
- 保留用户定义的别名（AS），如 SELECT CUSTOMERID AS CID → JSON 中用 CID
- 去掉表别名前缀，如 A.CUSTOMERID → JSON 中用 CUSTOMERID
- 系统字段（addWho/addTime/editWho/editTime）必须小驼峰

功能：
1. 从 SQL 或表名中提取字段信息（推荐从 SQL 提取，确保字段名一致）
2. 查询数据字典获取中文标签
3. 自动生成完整的表单 JSON 配置（4个items：settings + 主信息区块 + 自定义区块 + 其他区块）
4. 支持字段类型推断（input/combo/checkbox/fieldset）
5. 自动处理选择器配置（useAddon）
6. 自动处理字段分组（如批次属性）

使用方法：
    # 从 SQL 文件生成（推荐，确保字段名一致）
    python scripts/generate_form_json.py --sql-file query.sql --function-id C0104_TEST --output form_config.json

    # 从表名生成（查询所有字段，不推荐，字段名可能与 SQL 不一致）
    python scripts/generate_form_json.py --table-name UDF_BATCHTRCELABEL_CACHE --function-id C0104_TEST --output form_config.json

    # 指定字段列表生成
    python scripts/generate_form_json.py --fields ORGANIZATIONID WAREHOUSEID ASNNO SKU --function-id C0104_TEST --output form_config.json

    # 指定组织 ID
    python scripts/generate_form_json.py --sql-file query.sql --function-id C0104_TEST --org-id ND --output form_config.json

参数说明：
    --sql-file: SQL 文件路径（从 SQL 中提取字段）
    --table-name: 表名（查询该表的所有字段）
    --fields: 指定字段列表（空格分隔）
    --function-id: 功能编号（必填）
    --org-id: 组织 ID（默认：ND）
    --output: 输出文件路径（可选，不指定则输出到标准输出）
"""

import json
import argparse
import sys
from pathlib import Path

# 设置输出编码
sys.stdout.reconfigure(encoding='utf-8')

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database, query_table_dictionary, query_specific_fields, query_column_comments
from sql_parser import parse_sql_fields, parse_table_aliases


# ============================================================================
# 常量定义
# ============================================================================

# 系统字段（不放入主信息区块）
SYSTEM_FIELDS = {
    'UDF01', 'UDF02', 'UDF03', 'UDF04', 'UDF05', 'UDF06',
    'CURRENTVERSION', 'OPRSEQFLAG'
}

# 审计字段（放在其他区块）
AUDIT_FIELDS = {
    'ADDWHO', 'ADDTIME', 'EDITWHO', 'EDITTIME', 'CURRENTVERSION', 'OPRSEQFLAG'
}

# 需要添加选择器配置的字段
ADDON_FIELDS = {
    'WAREHOUSEID': {'type': 'WAREHOUSE', 'checkAuth': 'Y'},
    'CUSTOMERID': {'type': 'CUSTOMER', 'checkAuth': 'Y'},
    'SKU': {'type': 'SKU', 'checkAuth': 'Y'},
    'ORGANIZATIONID': {'type': 'ORGANIZATION', 'checkAuth': 'Y'},
}

# 批次属性字段（需要分组到 fieldset）
LOT_ATTRIBUTE_FIELDS = {
    'LOTATT01', 'LOTATT02', 'LOTATT03', 'LOTATT04', 'LOTATT05',
    'LOTATT06', 'LOTATT07', 'LOTATT08', 'LOTATT09', 'LOTATT10',
    'LOTATT11', 'LOTATT12'
}

# 自定义字段（放在自定义区块）
UDF_FIELDS = {'UDF01', 'UDF02', 'UDF03', 'UDF04', 'UDF05', 'UDF06'}

# 代码类型字段映射（用于 combo 类型）
CODE_TYPE_FIELDS = {
    'ASNSTATUS': 'ASN_STS',
    'ASNTYPE': 'ASN_TYP',
    'ACTIVEFLAG': 'YES_NO',
}



# ============================================================================
# 字段类型推断
# ============================================================================

def infer_field_type(field_name: str, field_info: dict = None) -> str:
    """
    推断字段类型

    Args:
        field_name: 字段名
        field_info: 字段信息（来自数据字典）

    Returns:
        字段类型（input/combo/checkbox/fieldset）
    """
    # 检查是否是代码类型字段
    if field_name.upper() in CODE_TYPE_FIELDS:
        return 'combo'

    # 检查是否是布尔类型字段
    if field_name.upper() in ['ACTIVEFLAG', 'ENABLEDFLAG', 'ISACTIVE']:
        return 'checkbox'

    # 默认返回 input
    return 'input'


def infer_fieldset_group(field_name: str) -> str:
    """
    推断字段分组

    Args:
        field_name: 字段名

    Returns:
        分组名称（如 'lot_Att'），如果不需要分组则返回 None
    """
    if field_name.upper() in LOT_ATTRIBUTE_FIELDS:
        return 'lot_Att'
    return None


# ============================================================================
# JSON 生成函数
# ============================================================================

def generate_settings_item(function_id: str, cid_start: int) -> dict:
    """
    生成 settings 全局配置（items[0]）

    Args:
        function_id: 功能编号
        cid_start: CID 起始值

    Returns:
        settings 配置字典
    """
    return {
        "type": "settings",
        "label": "",
        "hideItem": False,
        "firstOpenMore": False,
        "searchExpendConfig": True,
        "condfmt": [],
        "batchAddField": "",
        "position": "label-left",
        "inputWidth": "col-sm-25",
        "cid": f"c{cid_start}"
    }


def generate_main_block(function_id: str, fields: list, field_labels: dict,
                        cid_start: int, org_id: str = 'ND',
                        widget_name: str = 'headerGrid') -> dict:
    """
    生成主信息区块（items[1]）

    Args:
        function_id: 功能编号
        fields: 字段列表
        field_labels: 字段中文标签映射
        cid_start: CID 起始值
        org_id: 组织 ID

    Returns:
        主信息区块配置字典
    """
    # 提取主信息字段（排除系统字段、审计字段、UDF 字段、noteText）
    main_fields = []
    for field in fields:
        field_upper = field.upper()
        if field_upper in SYSTEM_FIELDS or field_upper in AUDIT_FIELDS:
            continue
        if field_upper.startswith('LOTATT'):
            continue  # 批次属性单独处理
        if field_upper == 'NOTETEXT':
            continue  # noteText 在自定义区块中已存在，避免重复
        main_fields.append(field)

    # 生成字段配置
    list_items = []
    current_cid = cid_start + 1

    # 按字段类型分组
    fieldset_groups = {}  # 用于存储分组字段
    standalone_fields = []  # 用于存储独立字段

    for field in main_fields:
        group = infer_fieldset_group(field)
        if group:
            if group not in fieldset_groups:
                fieldset_groups[group] = []
            fieldset_groups[group].append(field)
        else:
            standalone_fields.append(field)

    # 生成独立字段配置
    for field in standalone_fields:
        field_config = generate_field_config(field, field_labels.get(field, field),
                                              current_cid, org_id)
        list_items.append(field_config)
        current_cid += 1

    # 生成分组字段配置
    for group_name, group_fields in fieldset_groups.items():
        fieldset_config = generate_fieldset_config(group_name, group_fields,
                                                    field_labels, current_cid, org_id)
        list_items.append(fieldset_config)
        current_cid += len(group_fields) + 1

    # 构建区块
    if widget_name == 'detailsGrid':
        block_id = f"{function_id}DetailForm"
    else:
        block_id = f"{function_id}HeaderForm"
    return {
        "type": "block",
        "label": "主信息",
        "hideItem": False,
        "firstOpenMore": False,
        "searchExpendConfig": True,
        "condfmt": [],
        "batchAddField": "",
        "id": block_id,
        "schemeTmpName": block_id,
        "cid": f"c{cid_start}",
        "list": list_items
    }


def generate_field_config(field_name: str, udf_label: str, cid: int,
                          org_id: str = 'ND') -> dict:
    """
    生成单个字段配置

    Args:
        field_name: 字段名
        udf_label: 中文标签
        cid: CID 值
        org_id: 组织 ID

    Returns:
        字段配置字典
    """
    field_type = infer_field_type(field_name)

    # 基础配置
    config = {
        "type": field_type,
        "name": field_name,
        "label": "",
        "udfLabel": udf_label,
        "inputWidth": "col-sm-25",
        "isUdf": "Y",
        "udfFlag": "Y",
        "branchDefault": True,
        "hasFuzzyQuery": True,
        "schemeTmpName": field_name,
        "cid": f"c{cid}",
        "required": False,
        "value": "",
        "allowPaste": True
    }

    # 主信息区块字段：根据类型设置只读或禁用
    if field_type == 'combo':
        config["disabled"] = True  # 下拉框禁用
    else:
        config["readonly"] = True  # 输入框只读

    # 添加选择器配置
    if field_name.upper() in ADDON_FIELDS:
        addon_info = ADDON_FIELDS[field_name.upper()]
        config.update({
            "useAddon": True,
            "autoMate": True,
            "addonOptions": {"type": addon_info['type']},
            "udfAddonOptions": {
                "type": addon_info['type'],
                "input": {
                    "userdata": [{"checkAuth": addon_info['checkAuth']}],
                    "enableMultiselect": False
                }
            }
        })

    # 添加 combo 类型配置
    if field_type == 'combo':
        code_type = CODE_TYPE_FIELDS.get(field_name.upper(), 'YES_NO')
        config.update({
            "multiCheck": False,
            "optionsType": "SYSCODE",
            "codeType": code_type,
            "inputWidth": "col-sm-20"
        })

    # 添加 checkbox 类型配置
    if field_type == 'checkbox':
        config.update({
            "checked": True,
            "allowPaste": True,
            "branchDefault": True,
            "hasFuzzyQuery": True,
            "schemeTmpName": field_name,
            "cid": f"c{cid}"
        })

    # 小写审计字段处理
    if field_name.upper() in ['ADDWHO', 'ADDTIME', 'EDITWHO', 'EDITTIME']:
        config['name'] = field_name.lower()
        config['schemeTmpName'] = field_name.lower()

    return config


def generate_fieldset_config(group_name: str, fields: list, field_labels: dict,
                             cid_start: int, org_id: str = 'ND') -> dict:
    """
    生成分组字段配置（fieldset）

    Args:
        group_name: 分组名称
        fields: 字段列表
        field_labels: 字段中文标签映射
        cid_start: CID 起始值
        org_id: 组织 ID

    Returns:
        分组字段配置字典
    """
    # 生成组内字段配置
    list_items = []
    current_cid = cid_start + 1

    for field in fields:
        field_config = generate_field_config(field, field_labels.get(field, field),
                                              current_cid, org_id)
        list_items.append(field_config)
        current_cid += 1

    # 构建 fieldset
    return {
        "type": "fieldset",
        "name": group_name,
        "udfLabel": "批次属性",
        "width": "col-sm-100",
        "isUdf": "Y",
        "udfFlag": "Y",
        "list": list_items
    }


def generate_udf_block(function_id: str, fields: list, field_labels: dict,
                       cid_start: int, widget_name: str = 'headerGrid') -> dict:
    """
    生成自定义区块（items[2]）

    Args:
        function_id: 功能编号
        fields: 字段列表（包含 UDF 字段）
        field_labels: 字段中文标签映射
        cid_start: CID 起始值

    Returns:
        自定义区块配置字典
    """
    # 提取 UDF 字段和 noteText
    udf_fields = []
    has_note_text = False

    for field in fields:
        if field.upper() in UDF_FIELDS:
            udf_fields.append(field)
        if field.upper() == 'NOTETEXT':
            has_note_text = True

    # 生成字段配置
    list_items = []
    current_cid = cid_start + 1

    # 自定义字段标签映射：UDF01-UDF06 → 自定义01-自定义06
    udf_label_map = {
        'UDF01': '自定义01',
        'UDF02': '自定义02',
        'UDF03': '自定义03',
        'UDF04': '自定义04',
        'UDF05': '自定义05',
        'UDF06': '自定义06'
    }

    for field in udf_fields:
        # 优先使用映射的中文标签，如果没有则使用原始标签
        display_label = udf_label_map.get(field.upper(), field_labels.get(field, field))
        field_config = {
            "type": "input",
            "name": field,  # Keep original case for consistency with column config
            "label": "",
            "udfLabel": display_label,
            "inputWidth": "col-sm-25",
            "isUdf": "Y",
            "udfFlag": "Y",
            "branchDefault": True,
            "hasFuzzyQuery": True,
            "schemeTmpName": field,  # Keep original case
            "cid": f"c{current_cid}",
            "required": False,
            "readonly": False,
            "value": "",
            "allowPaste": True
        }
        list_items.append(field_config)
        current_cid += 1

    # 添加 noteText
    if has_note_text:
        note_config = {
            "type": "input",
            "name": "noteText",
            "label": "",
            "udfLabel": "备注",  # 固定显示为"备注"
            "inputWidth": "col-sm-100",
            "isUdf": "Y",
            "udfFlag": "Y",
            "branchDefault": True,
            "hasFuzzyQuery": True,
            "schemeTmpName": "noteText",
            "cid": f"c{current_cid}",
            "required": False,
            "readonly": False,
            "value": "",
            "allowPaste": True,
            "rows": "3"
        }
        list_items.append(note_config)

    # 构建区块
    if widget_name == 'detailsGrid':
        block_id = f"{function_id}DetailUdfForm"
    else:
        block_id = f"{function_id}HeaderUdfForm"
    return {
        "type": "block",
        "label": "自定义",
        "hideItem": False,
        "firstOpenMore": False,
        "searchExpendConfig": True,
        "condfmt": [],
        "batchAddField": "",
        "id": block_id,
        "schemeTmpName": block_id,
        "cid": f"c{cid_start}",
        "list": list_items
    }


def generate_other_block(function_id: str, cid_start: int,
                        widget_name: str = 'headerGrid') -> dict:
    """
    生成其他区块（items[3]）

    Args:
        function_id: 功能编号
        cid_start: CID 起始值

    Returns:
        其他区块配置字典
    """
    # 审计字段配置
    audit_fields = [
        {'name': 'addWho', 'label': '新增人员', 'transName': 'addWho_userName'},
        {'name': 'addTime', 'label': '新增时间'},
        {'name': 'editWho', 'label': '编辑人员', 'transName': 'editWho_userName'},
        {'name': 'editTime', 'label': '编辑时间'},
        {'name': 'currentVersion', 'label': '当前版本号'},
        {'name': 'oprSeqFlag', 'label': '操作流水标记', 'hidden': True}
    ]

    list_items = []
    current_cid = cid_start + 1

    for field_info in audit_fields:
        name = field_info['name']
        label = field_info['label']

        config = {
            "type": "input",
            "name": name,
            "label": "",
            "udfLabel": label,
            "inputWidth": "col-sm-25",
            "isUdf": "Y",
            "udfFlag": "Y",
            "branchDefault": True,
            "hasFuzzyQuery": True,
            "schemeTmpName": name,
            "cid": f"c{current_cid}",
            "required": False,
            "readonly": True,
            "value": "",
            "allowPaste": True
        }

        # 添加 transName 配置
        if 'transName' in field_info:
            config['transName'] = field_info['transName']
            config['defTransNameFlag'] = True

        # 添加 hidden 配置
        if 'hidden' in field_info:
            config['type'] = 'hidden'
            config['hidden'] = True

        list_items.append(config)
        current_cid += 1

    # 构建区块
    if widget_name == 'detailsGrid':
        block_id = f"{function_id}DetailOtherForm"
    else:
        block_id = f"{function_id}HeaderOtherForm"
    return {
        "type": "block",
        "label": "其他",
        "hideItem": False,
        "firstOpenMore": False,
        "searchExpendConfig": True,
        "condfmt": [],
        "batchAddField": "",
        "id": block_id,
        "position": "absolute",
        "schemeTmpName": block_id,
        "cid": f"c{cid_start}",
        "list": list_items
    }


# ============================================================================
# 主函数
# ============================================================================

def generate_form_json(function_id: str, fields: list = None,
                       sql_file: str = None, table_name: str = None,
                       org_id: str = 'ND', output_file: str = None,
                       widget_name: str = 'headerGrid') -> dict:
    """
    生成完整的表单 JSON 配置

    【优化】识别字段来自哪张表，分别查询每张表的数据字典，使用正确的 TABLENAME 查询条件

    Args:
        function_id: 功能编号
        fields: 字段列表（可选）
        sql_file: SQL 文件路径（可选）
        table_name: 表名（可选）
        org_id: 组织 ID
        output_file: 输出文件路径（可选）

    Returns:
        完整的表单 JSON 配置
    """
    # 加载数据库配置
    db_config = load_db_config()
    connection = connect_database(db_config)

    try:
        cursor = connection.cursor()

        # 获取字段列表和表别名映射
        field_info_list = None
        table_aliases = {}

        if sql_file:
            # 从 SQL 文件提取字段
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            field_info_list = parse_sql_fields(sql_content)
            # 解析 SQL 中的表别名映射
            table_aliases = parse_table_aliases(sql_content)
        elif table_name and not fields:
            # 从表名查询所有字段
            table_fields = query_table_dictionary(cursor, table_name, org_id=args.org_id)
            field_info_list = [{'field_name': f['field_name'], 'table_alias': None} for f in table_fields]

        if not field_info_list and not fields:
            raise ValueError("未指定字段、SQL 文件或表名")

        # 如果直接传入了字段列表（没有 SQL 文件），则构建简单的字段信息
        if fields and not field_info_list:
            field_info_list = [{'field_name': f, 'table_alias': None} for f in fields]

        # 提取纯字段名列表（用于生成 JSON）
        field_names = [f['field_name'] for f in field_info_list]

        # 查询字段中文标签
        # 【优化】识别字段来自哪张表，分别查询每张表的数据字典
        field_labels = {}

        # 按表别名分组字段，减少数据库查询次数
        table_fields_map = {}  # {'表别名': ['字段1', '字段2', ...]}
        for field_info in field_info_list:
            table_alias = field_info['table_alias']
            if table_alias:
                if table_alias not in table_fields_map:
                    table_fields_map[table_alias] = []
                table_fields_map[table_alias].append(field_info['field_name'])

        # 对每个表别名，查询该表的数据字典
        for table_alias, field_names_in_table in table_fields_map.items():
            # 根据表别名找到实际表名
            actual_table_name = table_aliases.get(table_alias.upper())

            if not actual_table_name:
                # 如果找不到表名，尝试直接使用表别名作为表名
                actual_table_name = table_alias

            # 使用正确的 TABLENAME 查询条件，批量查询该表的所有字段
            try:
                # 构建 IN 子句的占位符
                # 注意：数据字典中的字段名可能是小驼峰格式（如 organizationId）
                # 而 SQL 中的字段名可能是大写格式（如 ORGANIZATIONID）
                # 所以需要使用 UPPER() 函数进行不区分大小写的匹配
                placeholders = ','.join([f':field_{i}' for i in range(len(field_names_in_table))])
                params = {f'field_{i}': name.upper() for i, name in enumerate(field_names_in_table)}
                params['table_name'] = actual_table_name

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
                """, {**params, 'org_id': org_id})

                for row in cursor.fetchall():
                    # 优先使用 UDF_FIELDDESCR，如果为空则使用 FIELDDESCR
                    label = row[2] if row[2] else row[1]
                    if label:
                        # 使用原始字段名（大小写保持一致）作为键
                        # 数据字典中的字段名可能是小驼峰格式，需要匹配回原始字段名
                        original_field_name = next(
                            (f for f in field_names_in_table if f.upper() == row[0].upper()),
                            row[0]
                        )
                        field_labels[original_field_name] = label

            except Exception as e:
                print(f"警告: 查询表 {actual_table_name} 的数据字典失败: {e}")
                pass  # 查询失败则使用字段名本身

        # 兜底：对数据字典中找不到的字段，查询数据库表字段注释
        fields_missing_labels = {}
        # 找出哪些字段还没有标签
        for field_info in field_info_list:
            field_name = field_info['field_name']
            if field_name not in field_labels:
                actual_table_name = table_aliases.get(
                    field_info['table_alias'].upper()
                ) if field_info['table_alias'] else None
                if actual_table_name:
                    if actual_table_name not in fields_missing_labels:
                        fields_missing_labels[actual_table_name] = []
                    fields_missing_labels[actual_table_name].append(field_name)

        if fields_missing_labels:
            print("  [兜底] 对未找到数据字典标签的字段，查询数据库字段注释...")
            for table_name, missing_fields in fields_missing_labels.items():
                comments = query_column_comments(cursor, table_name, missing_fields)
                for field_name, comment in comments.items():
                    if comment and field_name not in field_labels:
                        field_labels[field_name] = comment
                        print(f"    ✓ 从字段注释获取: {field_name} → {comment}")

        # 生成 4 个 items
        cid_start = 10000

        # items[0]: settings
        settings = generate_settings_item(function_id, cid_start)

        # items[1]: 主信息区块
        main_block = generate_main_block(function_id, field_names, field_labels,
                                         cid_start + 1, org_id, widget_name)

        # items[2]: 自定义区块
        udf_block = generate_udf_block(function_id, field_names, field_labels,
                                        cid_start + 2, widget_name)

        # items[3]: 其他区块
        other_block = generate_other_block(function_id, cid_start + 3, widget_name)

        # 构建完整 JSON
        form_json = {
            "items": [settings, main_block, udf_block, other_block]
        }

        # 保存到文件
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(form_json, f, ensure_ascii=False, indent=2)
            print(f"表单 JSON 配置已保存到: {output_file}")

        return form_json

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description='FLUX WMS 表单 JSON 配置生成脚本')
    parser.add_argument('--sql-file', help='SQL 文件路径（从 SQL 中提取字段）')
    parser.add_argument('--table-name', help='表名（查询该表的所有字段）')
    parser.add_argument('--fields', nargs='+', help='指定字段列表（空格分隔）')
    parser.add_argument('--function-id', required=True, help='功能编号')
    parser.add_argument('--org-id', default='ND', help='组织 ID（默认：ND）')
    parser.add_argument('--widget-name', choices=['headerGrid', 'detailsGrid'], default='headerGrid',
                        help='组件名称（默认：headerGrid）')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--config', help='数据库配置文件路径（可选）')

    args = parser.parse_args()

    try:
        form_json = generate_form_json(
            function_id=args.function_id,
            fields=args.fields,
            sql_file=args.sql_file,
            table_name=args.table_name,
            org_id=args.org_id,
            output_file=args.output,
            widget_name=args.widget_name
        )

        # 如果没有指定输出文件，打印到标准输出
        if not args.output:
            print(json.dumps(form_json, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
