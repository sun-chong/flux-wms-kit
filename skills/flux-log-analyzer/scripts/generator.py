#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLUX WMS HTML 报告生成器

从 parser.py 输出的 JSON 数据生成 HTML 分析报告。
"""

import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from html import escape
from datetime import datetime


# ============================================================================
# 语法高亮配置
# ============================================================================

# SQL 关键字列表
SQL_KEYWORDS = [
    'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'JOIN', 'LEFT', 'RIGHT',
    'INNER', 'OUTER', 'ON', 'GROUP', 'BY', 'ORDER', 'ASC', 'DESC',
    'HAVING', 'LIMIT', 'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET',
    'DELETE', 'CREATE', 'ALTER', 'DROP', 'INDEX', 'TABLE', 'VIEW',
    'UNION', 'ALL', 'DISTINCT', 'AS', 'COUNT', 'SUM', 'AVG', 'MIN',
    'MAX', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'NOT', 'NULL',
    'IS', 'IN', 'EXISTS', 'BETWEEN', 'LIKE', 'IF', 'ROWNUM'
]

# 构建 SQL 关键字正则表达式（不区分大小写）
SQL_KEYWORD_PATTERN = re.compile(
    r'\b(' + '|'.join(SQL_KEYWORDS) + r')\b',
    re.IGNORECASE
)

# SQL 字符串模式
SQL_STRING_PATTERN = re.compile(r"'([^']*)'")

# SQL 数字模式
SQL_NUMBER_PATTERN = re.compile(r'\b(\d+(?:\.\d+)?)\b')

# JSON Key 模式
JSON_KEY_PATTERN = re.compile(r'"([^"]+)"\s*:')

# JSON 字符串值模式
JSON_STRING_PATTERN = re.compile(r':\s*"([^"]*)"')

# JSON 数字值模式
JSON_NUMBER_PATTERN = re.compile(r':\s*(\d+(?:\.\d+)?)')


# ============================================================================
# 语法高亮函数
# ============================================================================

def highlight_sql(sql: str) -> str:
    """
    为 SQL 语句添加语法高亮

    Args:
        sql: 原始 SQL 语句

    Returns:
        带有 HTML 标签的高亮 SQL
    """
    if not sql:
        return ''

    # 转义 HTML 特殊字符
    escaped = escape(sql)

    # 替换 SQL 关键字（使用占位符避免重复处理）
    placeholders = {}

    def replace_keyword(match):
        key = f'__KW_{len(placeholders)}__'
        placeholders[key] = f'<span class="sql-keyword">{match.group(0).upper()}</span>'
        return key

    escaped = SQL_KEYWORD_PATTERN.sub(replace_keyword, escaped)

    # 替换字符串
    def replace_string(match):
        key = f'__STR_{len(placeholders)}__'
        placeholders[key] = f'<span class="sql-string">\'{match.group(1)}\'</span>'
        return key

    escaped = SQL_STRING_PATTERN.sub(replace_string, escaped)

    # 替换数字
    def replace_number(match):
        key = f'__NUM_{len(placeholders)}__'
        placeholders[key] = f'<span class="sql-number">{match.group(1)}</span>'
        return key

    escaped = SQL_NUMBER_PATTERN.sub(replace_number, escaped)

    # 恢复所有占位符
    for key, value in placeholders.items():
        escaped = escaped.replace(key, value)

    return escaped


def highlight_json(json_str: str) -> str:
    """
    为 JSON 字符串添加语法高亮

    Args:
        json_str: 原始 JSON 字符串

    Returns:
        带有 HTML 标签的高亮 JSON
    """
    if not json_str:
        return ''

    # 转义 HTML 特殊字符
    escaped = escape(json_str)

    # 替换 JSON Key
    def replace_key(match):
        return f'<span class="json-key">"{match.group(1)}"</span>:'

    escaped = JSON_KEY_PATTERN.sub(replace_key, escaped)

    # 替换 JSON 字符串值
    def replace_string(match):
        return f': <span class="json-value-str">"{match.group(1)}"</span>'

    escaped = JSON_STRING_PATTERN.sub(replace_string, escaped)

    # 替换 JSON 数字值
    def replace_number(match):
        return f': <span class="json-value-num">{match.group(1)}</span>'

    escaped = JSON_NUMBER_PATTERN.sub(replace_number, escaped)

    return escaped


# ============================================================================
# HTML 模板加载
# ============================================================================

def load_template(template_path: str) -> str:
    """
    加载 HTML 模板

    Args:
        template_path: 模板文件路径

    Returns:
        模板内容

    Raises:
        FileNotFoundError: 模板文件不存在时抛出
    """
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(
            f"模板文件不存在: {template_path}\n"
            f"请先创建模板文件: templates/report.html"
        )

    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================================
# HTML 片段生成函数
# ============================================================================

def generate_timeline_items(
    phase_starts: List[Dict[str, Any]],
    sp_calls: List[Dict[str, Any]]
) -> str:
    """
    生成前后置操作时间线 HTML

    Args:
        phase_starts: 前后置开始记录列表
        sp_calls: SP 调用列表

    Returns:
        HTML 时间线字符串
    """
    items = []

    # 合并 phase_starts 和 sp_calls，按时间排序
    for phase in phase_starts:
        timestamp = escape(phase.get('timestamp', ''))
        user = escape(phase.get('user', ''))
        phase_type = escape(phase.get('phaseType', ''))
        function_id = escape(phase.get('functionId', ''))
        action_code = escape(phase.get('actionCode', ''))

        # 根据 phase_type 确定样式
        if '前置' in phase_type:
            css_class = 'pre'
            icon = '&#128315;'  # 左箭头
        else:
            css_class = 'post'
            icon = '&#128316;'  # 右箭头

        items.append({
            'timestamp': timestamp,
            'html': f'''
            <div class="timeline-item {css_class}">
                <div class="timeline-time">{timestamp} | {user}</div>
                <div class="timeline-content">
                    <strong>{icon} {phase_type}</strong><br>
                    功能模块: {function_id} | 动作代码: {action_code}
                </div>
            </div>
            '''
        })

    # 添加 SP 调用到时间线
    for sp in sp_calls:
        start_time = escape(sp.get('startTime', '') or '')
        sp_name = escape(sp.get('spName', ''))
        used_time = sp.get('usedTimeMs')
        result = escape(sp.get('result', '') or '')

        time_info = f'{used_time}ms' if used_time is not None else ''

        items.append({
            'timestamp': start_time,
            'html': f'''
            <div class="timeline-item sp">
                <div class="timeline-time">{start_time}</div>
                <div class="timeline-content">
                    <strong>&#128190; SP 调用: {sp_name}</strong>
                    {f'<br>耗时: {time_info}' if time_info else ''}
                    {f'<br>结果: {result}' if result else ''}
                </div>
            </div>
            '''
        })

    if not items:
        return '<div class="no-data">暂无前后置操作数据</div>'

    # 按时间戳排序（字符串比较，因为时间格式一致）
    items.sort(key=lambda x: x['timestamp'])

    # 提取 HTML 内容
    return '\n'.join(item['html'] for item in items)


# ============================================================================
# 主生成器类
# ============================================================================

class HTMLReportGenerator:
    """HTML 报告生成器"""

    def __init__(self, template_path: str):
        """
        初始化生成器

        Args:
            template_path: HTML 模板文件路径
        """
        self.template = load_template(template_path)

    def _transform_data(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 parser.py 输出的数据转换为模板期望的格式

        Args:
            json_data: parser.py 输出的 JSON 数据

        Returns:
            转换后的数据，符合模板期望的结构
        """
        # 输入验证
        if not json_data:
            raise ValueError("输入数据为空")

        metadata = json_data.get('metadata', {})
        if not metadata:
            raise ValueError("缺少 metadata 字段")

        statistics = json_data.get('statistics', {})
        sql_queries = json_data.get('sqlQueries', [])
        dml_statements = json_data.get('dmlStatements', [])
        pre_post_operations = json_data.get('prePostOperations', [])
        sp_calls = json_data.get('spCalls', [])
        exceptions = json_data.get('exceptions', [])
        wco_params = json_data.get('wcoParams', [])
        service_steps = json_data.get('serviceSteps', [])
        login_info = json_data.get('loginInfo', {})
        biz_data = json_data.get('bizData', {})

        # 提取 functionId 和 actionId
        function_id = ''
        action_id = ''
        if pre_post_operations:
            first_op = pre_post_operations[0]
            function_id = first_op.get('module', '')
            action_id = first_op.get('action', '')
        elif statistics.get('functionModules'):
            function_modules = statistics['functionModules']
            if function_modules:
                function_id = function_modules[0] if isinstance(function_modules, list) else function_modules
        if statistics.get('actionCodes'):
            action_codes = statistics['actionCodes']
            if action_codes:
                action_id = action_codes[0] if isinstance(action_codes, list) else action_codes

        # 构建 meta 对象
        meta = {
            'fileName': metadata.get('fileName', ''),
            'totalLines': metadata.get('totalLines', 0),
            'timeRange': metadata.get('timeRange', {}),
            'organizationId': metadata.get('organizationId', ''),
            'warehouseId': metadata.get('warehouseId', ''),
            'userId': metadata.get('users', [''])[0] if metadata.get('users') else '',
            'userName': metadata.get('users', [''])[0] if metadata.get('users') else '',
            'functionId': function_id,
            'actionId': action_id
        }

        # 构建 overview 对象
        sql_count = statistics.get('sqlQueryCount', len(sql_queries))
        dml_count = statistics.get('dmlStatementCount', len(dml_statements))
        avg_time = statistics.get('avgSqlTimeMs', 0)
        if isinstance(avg_time, float):
            avg_time = round(avg_time, 1)

        overview = {
            'sqlCount': sql_count,
            'sqlAvgTime': avg_time,
            'slowQueryCount': statistics.get('slowQueryCount', 0),
            'prePostCount': len(pre_post_operations),
            'spCallCount': len(sp_calls),
            'dmlCount': dml_count,
            'errorCount': len(exceptions)
        }

        # 使用 parser 输出的 prePostEvents
        pre_post_events = json_data.get('prePostEvents', [])

        # 转换 sqlQueries（合并 sql_queries 和 dml_statements）
        sql_queries_list = []
        for q in sql_queries:
            query_item = {
                'type': 'query',
                'line': q.get('line', 0),
                'timestamp': q.get('timestamp', ''),
                'sqlType': q.get('sqlType', 'SELECT'),
                'sql': q.get('sql', ''),
                'sqlOriginal': q.get('sql', ''),
                'resultCount': q.get('resultCount', 0),
                'usedTime': q.get('usedTimeMs', 0),
                'table': self._extract_table_name(q.get('sql', ''))
            }
            sql_queries_list.append(query_item)

        for d in dml_statements:
            dml_item = {
                'type': 'dml',
                'line': d.get('line', 0),
                'timestamp': d.get('timestamp', ''),
                'sqlType': self._extract_dml_type(d.get('sql', '')),
                'sql': d.get('sql', ''),
                'sqlOriginal': d.get('sql', ''),
                'params': d.get('params'),  # 参数值（JSON 数组字符串）
                'affectedRows': d.get('affectedRows', 0),
                'usedTime': d.get('usedTimeMs', 0),
                'table': self._extract_table_name(d.get('sql', ''))
            }
            sql_queries_list.append(dml_item)

        # 转换 errors
        errors = []
        for exc in exceptions:
            # 获取 causedByChain，如果为空则从 causedBy 构建
            caused_by_chain = exc.get('causedByChain', [])
            if not caused_by_chain:
                caused_by = exc.get('causedBy', '')
                caused_by_msg = exc.get('causedByMessage', '')
                if caused_by:
                    chain_item = caused_by
                    if caused_by_msg:
                        chain_item += ': ' + caused_by_msg
                    caused_by_chain = [chain_item]

            error = {
                'type': exc.get('exceptionType', 'Exception'),
                'message': exc.get('message', '') or exc.get('errorMessage', ''),
                'line': exc.get('line', 0),
                'startLine': exc.get('line', 0),
                'endLine': exc.get('line', 0),
                'code': exc.get('errorCode', ''),
                'fullStack': exc.get('fullStack', ''),
                'causedByChain': caused_by_chain,
                'projectCodeLines': exc.get('projectCodeLines', [])
            }
            errors.append(error)

        # 转换 config（WCO 参数）
        config_params = []
        for wco in wco_params:
            config = {
                'configId': wco.get('paramName', ''),
                'value': wco.get('paramValue', ''),
                'defaultValue': wco.get('defaultValue', ''),
                'matchResult': wco.get('matchResult', ''),
                'filters': {
                    'filterConditions': wco.get('filterConditions', ''),
                    'paramName': wco.get('paramName', ''),
                    'paramValue': wco.get('paramValue', '')
                }
            }
            config_params.append(config)

        # 转换 serviceSteps
        service_steps_list = []
        for step in service_steps:
            step_item = {
                'stepNo': step.get('stepNo', 0),
                'logicModel': step.get('logicModel', ''),
                'startTime': step.get('startTime', ''),
                'endTime': step.get('endTime', ''),
                'result': step.get('result', ''),
                'timestamp': step.get('timestamp', ''),
                'user': step.get('user', ''),
                'line': step.get('line', 0),
                'details': step.get('details', '')
            }
            service_steps_list.append(step_item)

        # 构建最终结果
        result = {
            'meta': meta,
            'overview': overview,
            'prePostEvents': pre_post_events,
            'sqlQueries': sql_queries_list,
            'dmlOperations': [d for d in sql_queries_list if d['type'] == 'dml'],
            'errors': errors,
            'configParams': config_params,
            'serviceSteps': service_steps_list,
            'loginInfo': login_info,
            'bizData': biz_data
        }

        return result

    def _extract_table_name(self, sql: str) -> str:
        """
        从 SQL 语句中提取表名

        Args:
            sql: SQL 语句

        Returns:
            表名或空字符串
        """
        if not sql:
            return ''

        sql_upper = sql.upper().strip()

        # SELECT 查询
        if sql_upper.startswith('SELECT'):
            # FROM table_name
            from_match = re.search(r'FROM\s+(\w+)', sql_upper)
            if from_match:
                return from_match.group(1)
            # INTO table_name
            into_match = re.search(r'INTO\s+(\w+)', sql_upper)
            if into_match:
                return into_match.group(1)

        # INSERT 查询
        if sql_upper.startswith('INSERT'):
            into_match = re.search(r'INTO\s+(\w+)', sql_upper)
            if into_match:
                return into_match.group(1)

        # UPDATE 查询
        if sql_upper.startswith('UPDATE'):
            update_match = re.search(r'UPDATE\s+(\w+)', sql_upper)
            if update_match:
                return update_match.group(1)

        # DELETE 查询
        if sql_upper.startswith('DELETE'):
            from_match = re.search(r'FROM\s+(\w+)', sql_upper)
            if from_match:
                return from_match.group(1)

        return ''

    def _extract_dml_type(self, sql: str) -> str:
        """
        从 DML 语句中提取类型

        Args:
            sql: DML 语句

        Returns:
            DML 类型（INSERT/UPDATE/DELETE）
        """
        if not sql:
            return 'UNKNOWN'

        sql_upper = sql.upper().strip()
        if sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        return 'UNKNOWN'

    def generate(self, json_data: Dict[str, Any], output_path: str) -> str:
        """
        生成 HTML 报告

        Args:
            json_data: parser.py 输出的 JSON 数据
            output_path: HTML 输出文件路径

        Returns:
            输出文件路径
        """
        # 转换数据格式
        transformed_data = self._transform_data(json_data)

        # 生成页面标题
        file_name = transformed_data.get('meta', {}).get('fileName', '未知文件')
        page_title = f'FLUX WMS 日志分析报告 - {file_name}'

        # 将转换后的数据转换为 JSON 字符串
        log_data_json = json.dumps(transformed_data, ensure_ascii=False, indent=2)

        # 替换模板占位符
        html = self.template
        html = html.replace('{{PAGE_TITLE}}', page_title)
        html = html.replace('{{LOG_DATA}}', log_data_json)

        # 确保输出目录存在
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return output_path


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='FLUX WMS HTML 报告生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python generator.py result.json
  python generator.py result.json --template templates/report.html
  python generator.py result.json --output outputs/html/report.html
        '''
    )

    parser.add_argument(
        'json_file',
        help='parser.py 输出的 JSON 文件路径'
    )

    parser.add_argument(
        '--template', '-t',
        default=str(Path(__file__).parent.parent / 'templates' / 'report.html'),
        help='HTML 模板文件路径（默认: templates/report.html）'
    )

    parser.add_argument(
        '--output', '-o',
        help='HTML 输出文件路径（默认: outputs/html/<原文件名>.html）'
    )

    args = parser.parse_args()

    # 检查 JSON 文件是否存在
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"错误: JSON 文件不存在 - {args.json_file}", file=__import__('sys').stderr)
        __import__('sys').exit(1)

    # 读取 JSON 数据
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败 - {e}", file=__import__('sys').stderr)
        __import__('sys').exit(1)

    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        # 使用 JSON 文件名生成输出路径，自动添加当天日期
        json_stem = json_path.stem
        today = datetime.now().strftime('%Y%m%d')
        output_dir = Path(__file__).parent.parent.parent.parent.parent / 'outputs' / 'html'
        output_path = str(output_dir / f'{json_stem}_analysis_{today}.html')

    # 创建生成器并生成报告
    try:
        generator = HTMLReportGenerator(args.template)
        result_path = generator.generate(json_data, output_path)
        print(f"HTML 报告已生成: {result_path}")
    except FileNotFoundError as e:
        print(f"错误: {e}", file=__import__('sys').stderr)
        __import__('sys').exit(1)
    except Exception as e:
        print(f"错误: 生成报告失败 - {e}", file=__import__('sys').stderr)
        __import__('sys').exit(1)


if __name__ == '__main__':
    main()
