#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLUX WMS 日志分析 SKILL 集成测试

测试 parser.py 和 generator.py 的完整流程。
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from parser import FLUXWMSLogParser
from generator import HTMLReportGenerator


def parse_log_file(log_file: str) -> dict:
    """解析日志文件并返回结果字典"""
    log_parser = FLUXWMSLogParser()
    return log_parser.parse_file(log_file)


def generate_report(json_file: str, template_file: str, output_file: str) -> None:
    """从 JSON 文件生成 HTML 报告"""
    with open(json_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    generator = HTMLReportGenerator(template_file)
    generator.generate(json_data, output_file)


def test_parse_log_file():
    """测试日志解析"""
    log_file = 'log/Untitled-1.log'

    # 解析日志
    result = parse_log_file(log_file)

    # 验证基本结构
    assert 'metadata' in result, "缺少 metadata"
    assert 'sqlQueries' in result, "缺少 sqlQueries"
    assert 'dmlStatements' in result, "缺少 dmlStatements"
    assert 'prePostOperations' in result, "缺少 prePostOperations"
    assert 'spCalls' in result, "缺少 spCalls"
    assert 'exceptions' in result, "缺少 exceptions"
    assert 'wcoParams' in result, "缺少 wcoParams"
    assert 'statistics' in result, "缺少 statistics"

    # 验证元数据
    metadata = result['metadata']
    assert metadata['fileName'] == 'Untitled-1.log', f"文件名错误: {metadata['fileName']}"
    assert metadata['totalLines'] > 0, "总行数应大于 0"
    assert len(metadata['users']) > 0, "应至少有一个用户"

    # 验证统计数据
    stats = result['statistics']
    # parser.py 返回的是 snake_case 字段名
    assert stats['sql_query_count'] > 0, "SQL 查询数应大于 0"
    assert stats['dml_statement_count'] > 0, "DML 语句数应大于 0"

    print(f"  [PASS] 解析测试通过")
    print(f"    - SQL 查询: {stats['sql_query_count']}")
    print(f"    - DML 语句: {stats['dml_statement_count']}")
    print(f"    - 前后置操作: {stats['pre_post_operation_count']}")
    print(f"    - SP 调用: {stats['sp_call_count']}")
    print(f"    - 异常: {stats['exception_count']}")

    return result


def test_generate_report():
    """测试 HTML 报告生成"""
    log_file = 'log/Untitled-1.log'
    template_file = '.claude/skills/flux-wms-log-analyzer/templates/report.html'

    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = os.path.join(tmpdir, 'test.json')
        output_file = os.path.join(tmpdir, 'test_report.html')

        # 解析日志
        data = parse_log_file(log_file)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 生成 HTML
        generate_report(json_file, template_file, output_file)

        # 验证 HTML 文件
        assert os.path.exists(output_file), "HTML 文件未生成"

        with open(output_file, 'r', encoding='utf-8') as f:
            html = f.read()

        assert len(html) > 1000, f"HTML 文件太小: {len(html)} bytes"
        assert 'FLUX WMS' in html, "缺少页面标题"
        assert 'stat-card' in html, "缺少统计卡片"
        assert 'code-block' in html, "缺少代码块"

        print(f"  [PASS] 生成测试通过")
        print(f"    - HTML 大小: {len(html)} bytes")

        # 复制到 outputs/html 以便检查
        output_dir = 'outputs/html'
        os.makedirs(output_dir, exist_ok=True)
        final_output = os.path.join(output_dir, 'Untitled-1_analysis_20260616.html')
        shutil.copy(output_file, final_output)
        print(f"    - 测试报告已保存到: {final_output}")


def main():
    """主测试函数"""
    print("=" * 60)
    print("FLUX WMS 日志分析 SKILL 集成测试")
    print("=" * 60)
    print()

    test_results = {}

    # 测试日志解析
    print("日志解析:")
    try:
        test_parse_log_file()
        test_results['parse'] = True
    except Exception as e:
        print(f"  [FAIL] 解析测试失败: {e}")
        test_results['parse'] = False

    print()

    # 测试 HTML 生成
    print("HTML 生成:")
    try:
        test_generate_report()
        test_results['generate'] = True
    except Exception as e:
        print(f"  [FAIL] 生成测试失败: {e}")
        test_results['generate'] = False

    print()
    print("=" * 60)
    print("测试结果:")
    print("=" * 60)
    for test_name, passed in test_results.items():
        status = "[PASS] 通过" if passed else "[FAIL] 失败"
        print(f"  {test_name}: {status}")

    print()
    all_passed = all(test_results.values())
    if all_passed:
        print("=" * 60)
        print("所有测试通过 [PASS]")
        print("=" * 60)
    else:
        print("=" * 60)
        print("部分测试失败 [FAIL]")
        print("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()
