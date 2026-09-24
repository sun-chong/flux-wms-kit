#!/usr/bin/env python3
"""
FLUX WMS 报表配置验证工具
验证 DEV_UDFFUNCFG_WIDGET 表中的 JSON 配置
"""

import json
import argparse
import sys
from pathlib import Path

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database


def verify_record_exists(cursor, function_id: str, widget_name: str, org_id: str = 'ND') -> bool:
    """验证记录是否存在"""
    cursor.execute("""
        SELECT COUNT(*) FROM DEV_UDFFUNCFG_WIDGET
        WHERE ORGANIZATIONID = :org_id
          AND FUNCTIONID = :func_id
          AND WIDGETNAME = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})

    count = cursor.fetchone()[0]
    return count > 0


def get_json_data(cursor, function_id: str, widget_name: str, org_id: str = 'ND') -> str:
    """获取 JSON 数据"""
    cursor.execute("""
        SELECT JSONDATA FROM DEV_UDFFUNCFG_WIDGET
        WHERE ORGANIZATIONID = :org_id
          AND FUNCTIONID = :func_id
          AND WIDGETNAME = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})

    result = cursor.fetchone()
    if result and result[0]:
        # CLOB 类型需要 .read()
        return result[0].read()
    return None


def verify_json_structure(json_str: str) -> dict:
    """验证 JSON 结构"""
    try:
        json_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {'valid': False, 'error': f'JSON 解析错误: {e}'}

    errors = []

    # 检查顶层结构
    if 'items' not in json_data:
        errors.append("缺少 'items' 数组")
    if 'gridPro' not in json_data:
        errors.append("缺少 'gridPro' 数组")
    if 'rightMenu' not in json_data:
        errors.append("缺少 'rightMenu' 数组")

    # 检查 items 数组
    if 'items' in json_data:
        if not isinstance(json_data['items'], list):
            errors.append("'items' 必须是数组")
        else:
            for i, item in enumerate(json_data['items']):
                # 检查必填字段
                required_fields = ['id', 'field', 'label', 'udfLabel', 'width', 'sort', 'align', 'type',
                                 'filterType', 'calTpl', 'isCal', 'udfFormat', 'conFormName', 'conFormField',
                                 'connector', 'systemCode', 'udfFlag', 'isUdf', 'cid', 'readonly']

                for field in required_fields:
                    if field not in item:
                        errors.append(f"items[{i}] 缺少必填字段: {field}")

                # 检查小驼峰字段
                if 'field' in item:
                    field_name = item['field']
                    if field_name in ['ADDWHO', 'ADDTIME', 'EDITWHO', 'EDITTIME']:
                        errors.append(f"items[{i}] 字段 '{field_name}' 必须使用小驼峰形式")

    # 检查 gridPro 数组
    if 'gridPro' in json_data:
        if not isinstance(json_data['gridPro'], list):
            errors.append("'gridPro' 必须是数组")
        elif len(json_data['gridPro']) > 0:
            grid = json_data['gridPro'][0]
            if 'widgetName' not in grid:
                errors.append("gridPro[0] 缺少 'widgetName' 字段")
            elif grid['widgetName'] not in ['headerGrid', 'detailsGrid']:
                errors.append(f"gridPro[0].widgetName 值无效: {grid['widgetName']}")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'data': json_data
    }


def verify_chinese_characters(json_data: dict) -> list:
    """验证中文字符"""
    issues = []

    if 'items' in json_data:
        for i, item in enumerate(json_data['items']):
            if 'udfLabel' in item:
                label = item['udfLabel']
                # 检查是否有乱码或编码问题
                if label and not all(ord(c) < 0x10000 for c in label):
                    issues.append(f"items[{i}].udfLabel 可能包含异常字符: {label}")

    return issues


def verify_field_names(json_data: dict) -> dict:
    """验证字段名"""
    result = {
        'camel_case_fields': [],
        'uppercase_fields': [],
        'issues': []
    }

    if 'items' in json_data:
        for i, item in enumerate(json_data['items']):
            if 'field' in item:
                field_name = item['field']

                # 检查是否为小驼峰字段
                if field_name in ['addWho', 'addTime', 'editWho', 'editTime']:
                    result['camel_case_fields'].append(field_name)
                elif field_name in ['ADDWHO', 'ADDTIME', 'EDITWHO', 'EDITTIME']:
                    result['uppercase_fields'].append(field_name)
                    result['issues'].append(f"items[{i}].field 使用了大写形式: {field_name}，应使用小驼峰")

    return result


def print_verification_report(function_id: str, widget_name: str, verification_results: dict):
    """打印验证报告"""
    print(f"\n{'='*60}")
    print(f"FLUX WMS 报表配置验证报告")
    print(f"{'='*60}")
    print(f"功能编号: {function_id}")
    print(f"组件名称: {widget_name}")
    print(f"{'='*60}\n")

    # 记录存在性验证
    print(f"1. 记录存在性验证:")
    if verification_results['record_exists']:
        print(f"   ✓ 记录存在")
    else:
        print(f"   ✗ 记录不存在")
        return

    # JSON 结构验证
    print(f"\n2. JSON 结构验证:")
    json_validation = verification_results['json_validation']
    if json_validation['valid']:
        print(f"   ✓ JSON 结构有效")
    else:
        print(f"   ✗ JSON 结构无效:")
        for error in json_validation['errors']:
            print(f"     - {error}")

    # 中文字符验证
    print(f"\n3. 中文字符验证:")
    chinese_issues = verification_results['chinese_issues']
    if not chinese_issues:
        print(f"   ✓ 中文字符正常")
    else:
        print(f"   ⚠ 中文字符问题:")
        for issue in chinese_issues:
            print(f"     - {issue}")

    # 字段名验证
    print(f"\n4. 字段名验证:")
    field_verification = verification_results['field_verification']
    if not field_verification['issues']:
        print(f"   ✓ 字段名正确")
    else:
        print(f"   ✗ 字段名问题:")
        for issue in field_verification['issues']:
            print(f"     - {issue}")

    # 统计信息
    print(f"\n5. 统计信息:")
    if 'data' in json_validation and json_validation['data']:
        data = json_validation['data']
        if 'items' in data:
            print(f"   - 列数: {len(data['items'])}")
        if 'gridPro' in data and data['gridPro']:
            print(f"   - 网格类型: {data['gridPro'][0].get('widgetName', 'N/A')}")

    # 小驼峰字段统计
    if field_verification['camel_case_fields']:
        print(f"   - 小驼峰字段: {', '.join(field_verification['camel_case_fields'])}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='FLUX WMS 报表配置验证工具')
    parser.add_argument('function_id', help='功能编号 (FUNCTIONID)')
    parser.add_argument('--widget-name', default='headerGrid',
                       choices=['headerGrid', 'detailsGrid'],
                       help='组件名称 (默认: headerGrid)')
    parser.add_argument('--config', help='数据库配置文件路径 (可选)')
    parser.add_argument('--org-id', default='ND', help='组织 ID（默认: ND）')
    parser.add_argument('--export', help='导出 JSON 到指定文件')

    args = parser.parse_args()

    # 加载数据库配置
    try:
        db_config = load_db_config(args.config)
    except Exception as e:
        print(f"错误: 无法加载数据库配置: {e}")
        sys.exit(1)

    # 连接数据库
    try:
        connection = connect_database(db_config)
    except Exception as e:
        print(f"错误: 无法连接数据库: {e}")
        sys.exit(1)

    try:
        cursor = connection.cursor()

        # 1. 验证记录是否存在
        record_exists = verify_record_exists(cursor, args.function_id, args.widget_name, args.org_id)

        if not record_exists:
            print(f"错误: 记录不存在 (FUNCTIONID={args.function_id}, WIDGETNAME={args.widget_name})")
            sys.exit(1)

        # 2. 获取 JSON 数据
        json_str = get_json_data(cursor, args.function_id, args.widget_name, args.org_id)

        if not json_str:
            print(f"错误: 无法获取 JSON 数据")
            sys.exit(1)

        # 3. 验证 JSON 结构
        json_validation = verify_json_structure(json_str)

        # 4. 验证中文字符
        chinese_issues = []
        if json_validation['valid'] and json_validation['data']:
            chinese_issues = verify_chinese_characters(json_validation['data'])

        # 5. 验证字段名
        field_verification = {'camel_case_fields': [], 'uppercase_fields': [], 'issues': []}
        if json_validation['valid'] and json_validation['data']:
            field_verification = verify_field_names(json_validation['data'])

        # 打印验证报告
        verification_results = {
            'record_exists': record_exists,
            'json_validation': json_validation,
            'chinese_issues': chinese_issues,
            'field_verification': field_verification
        }

        print_verification_report(args.function_id, args.widget_name, verification_results)

        # 导出 JSON（如果指定）
        if args.export and json_validation['valid'] and json_validation['data']:
            export_path = Path(args.export)
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(json_validation['data'], f, ensure_ascii=False, indent=2)
            print(f"JSON 已导出到: {args.export}")

        # 返回验证结果
        if not json_validation['valid'] or field_verification['issues']:
            sys.exit(1)

    finally:
        connection.close()


if __name__ == '__main__':
    main()
