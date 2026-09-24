#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLUX WMS 日志解析器

解析 FLUX WMS 系统日志文件，提取 SQL 查询、DML 语句、SP 调用、异常等信息。
"""

import re
import json
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from pathlib import Path


# ============================================================================
# 正则表达式模式定义
# ============================================================================

# 日志行格式: YYYY-MM-DD HH:MM:SS:ms: (用户)内容
LOG_LINE_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}:\d{3}):\s+\((\w+)\)(.*)$')

# SQL 查询模式: 查询结果:N (usedTime:N) SQL
SQL_QUERY_PATTERN = re.compile(r'查询结果:(\d+)\s+\(usedTime:(\d+)\)\s+(.*)$')

# DML 语句模式: 影响行数:N (usedTime:N) SQL
DML_PATTERN = re.compile(r'影响行数:(\d+)\s+\(usedTime:(\d+)\)\s+(.*)$')

# 前后置操作模式: 当前调用模式为前置|后置事务外|内;当前功能模块为:XX;动作代码:XX
# 动作代码只匹配字母、数字、下划线，不匹配中文和特殊字符
PRE_POST_PATTERN = re.compile(r'当前调用模式为(前置|后置)事务(外|内);当前功能模块为:(\S+);动作代码:([A-Za-z0-9_]+)')

# 前后置开始模式: (前置开始|前置_IN开始|后置开始|后置_IN开始)扩展操作:功能编号:XX,动作代码:XX
PHASE_START_PATTERN = re.compile(r'\((前置开始|前置_IN开始|后置开始|后置_IN开始)\)扩展操作:功能编号:(\S+),动作代码:(\S+)')

# 前后置成功/失败模式: (前置成功(...)|前置_IN成功(...)|后置成功(...)|后置_IN成功(...))扩展操作:功能编号:XX,动作代码:XX
PHASE_RESULT_PATTERN = re.compile(r'\((前置|后置)(_IN)?(成功|失败)\(([^)]+)\)\)扩展操作:功能编号:(\S+),动作代码:(\S+)')

# 扩展操作传参数据模式: 扩展操作传参相关数据:{...}
EXT_PARAMS_PATTERN = re.compile(r'扩展操作传参相关数据:\{(.+)\}$')

# SP 事务内调用模式: 当前模式为自定义SP事务内调用，参数信息：{...} 或 返回信息：{...}
SP_INVOKE_PATTERN = re.compile(r'当前模式为自定义SP事务内调用，(参数信息|返回信息)：(\{.+?\})(?=当前模式|当前调用|$)')

# SP 调用开始模式: (时间戳)START excute SP:名称
SP_START_PATTERN = re.compile(r'\((\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}:\d{3})\)START excute SP:(\S+)')

# SP 调用结束模式: (时间戳)END excute SP:名称
SP_END_PATTERN = re.compile(r'\((\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}:\d{3})\)END excute SP:(\S+)')

# 自定义服务步骤开始模式: seqNo=N logicModel=XXX start
SERVICE_STEP_START_PATTERN = re.compile(r'seqNo=(\d+)\s+logicModel=(\S+)\s+start', re.IGNORECASE)

# 自定义服务步骤结束模式: result=OK|ERROR seqNo=N logicModel=XXX end
SERVICE_STEP_END_PATTERN = re.compile(r'result=(\w+)\s+seqNo=(\d+)\s+logicModel=(\S+)\s+end', re.IGNORECASE)

# SP 执行结果模式: 执行SP:EXEC SP名称 参数||结果:{{结果}}
SP_EXEC_PATTERN = re.compile(r'执行SP:EXEC\s+(\S+)\s+(.*?)\|\|结果:\{(\{.+\})\}')

# 异常模式: Exception 或 Error
EXCEPTION_PATTERN = re.compile(r'(?:Exception|Error)(?:\s*:\s*(.*))?$')

# Caused by 模式
CAUSED_BY_PATTERN = re.compile(r'Caused by:\s+(\S+(?:\.\S+)*)(?:\s*:\s*(.*))?$')

# WCO 参数模式: WCO参数:XX=XX,其中筛选条件为:{...},WCO匹配结果为：XX,...
WCO_PATTERN = re.compile(r'WCO参数:(\w+)=(.*?),其中筛选条件为:\{(.+?)\},WCO匹配结果为：(.+?)(?:,取表头默认值:(.*))?$')

# 带参数占位符的 DML 模式: [N] (usedTime:N) SQL...（下一行是 JSON 参数数组）
DML_PARAM_PATTERN = re.compile(r'\[(\d+)\]\s+\(usedTime:(\d+)\)\s+(.*)$')

# 错误码模式: 0X~错误码~错误消息~标志
ERROR_CODE_PATTERN = re.compile(r'^0X~(.+?)~(.+?)~(.+)$')

# SP 执行错误模式: 执行SP:名称 ... 结果:{{错误码#消息}}
SP_EXEC_ERROR_PATTERN = re.compile(r'执行SP:(\S+)\s+.*结果:\{\{(\d+)#(.+?)\}\}')

# 前置事务执行异常模式: (前置_IN执行异常)扩展操作:功能模块,动作代码
PRE_POST_EXCEPTION_PATTERN = re.compile(r'\((前置|后置)(_IN)?执行异常\)扩展操作:(\S+),(\S+)')

# 慢查询阈值（毫秒）
SLOW_QUERY_THRESHOLD_MS = 100


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class SQLQuery:
    """SQL 查询记录"""
    timestamp: str
    user: str
    resultCount: int
    usedTimeMs: int
    sql: str
    isSlowQuery: bool = False
    line: int = 0


@dataclass
class DMLStatement:
    """DML 语句记录"""
    timestamp: str
    user: str
    affectedRows: int
    usedTimeMs: int
    sql: str
    params: Optional[str] = None  # 参数值（当 SQL 含 ? 时，下一行的 JSON 数组）
    line: int = 0


@dataclass
class PrePostOperation:
    """前后置操作记录"""
    timestamp: str
    user: str
    phase: str
    scope: str
    module: str
    action: str
    line: int = 0
    params: Optional[str] = None  # 扩展操作传参数据
    spResult: Optional[str] = None  # SP 事务内调用结果


@dataclass
class PhaseStart:
    """前后置开始记录"""
    timestamp: str
    user: str
    phaseType: str
    functionId: str
    actionCode: str
    result: Optional[str] = None  # 成功/失败状态
    resultDetail: Optional[str] = None  # 成功/失败详情
    line: int = 0


@dataclass
class PrePostEvent:
    """前后置事件（用于时间线展示）"""
    timestamp: str
    user: str
    eventType: str  # 前置事务外、前置事务内、后置事务外、后置事务内、扩展操作开始、扩展操作成功、扩展操作失败
    functionId: str
    actionCode: str
    line: int = 0
    extParams: Optional[str] = None  # 扩展操作传参数据
    spInvokeParams: Optional[str] = None  # SP 事务内调用参数
    spInvokeResult: Optional[str] = None  # SP 事务内调用返回
    spCalls: List[Dict] = None  # SP 调用信息列表

    def __post_init__(self):
        if self.spCalls is None:
            self.spCalls = []


@dataclass
class SPCall:
    """SP 调用记录"""
    spName: str
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    executionSql: Optional[str] = None
    result: Optional[str] = None
    usedTimeMs: Optional[int] = None
    line: int = 0


@dataclass
class ServiceStep:
    """自定义服务步骤记录"""
    stepNo: int
    logicModel: str
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    result: Optional[str] = None  # OK, ERROR
    timestamp: str = ''
    user: str = ''
    line: int = 0
    details: Optional[str] = None  # 步骤的详细信息


@dataclass
class ExceptionInfo:
    """异常信息"""
    timestamp: str
    user: str
    exceptionType: str
    message: Optional[str] = None
    causedBy: Optional[str] = None
    causedByMessage: Optional[str] = None
    causedByChain: List[str] = None  # 多层 Caused by 链
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None
    fullStack: Optional[str] = None
    line: int = 0

    def __post_init__(self):
        if self.causedByChain is None:
            self.causedByChain = []


@dataclass
class WCOParam:
    """WCO 参数记录"""
    timestamp: str
    user: str
    paramName: str
    paramValue: str
    filterConditions: str
    matchResult: str
    defaultValue: Optional[str] = None
    line: int = 0


@dataclass
class LoginInfo:
    """登录信息"""
    userId: Optional[str] = None
    userName: Optional[str] = None
    warehouseId: Optional[str] = None
    organizationId: Optional[str] = None
    sessionId: Optional[str] = None
    clientIp: Optional[str] = None


@dataclass
class BizData:
    """业务数据"""
    functionId: Optional[str] = None
    actionId: Optional[str] = None
    documentNo: Optional[str] = None


@dataclass
class Statistics:
    """统计数据"""
    totalLines: int = 0
    sqlQueryCount: int = 0
    dmlStatementCount: int = 0
    spCallCount: int = 0
    exceptionCount: int = 0
    slowQueryCount: int = 0
    wcoParamCount: int = 0
    prePostOperationCount: int = 0
    totalSqlTimeMs: int = 0
    totalDmlTimeMs: int = 0
    avgSqlTimeMs: float = 0.0
    avgDmlTimeMs: float = 0.0
    maxSqlTimeMs: int = 0
    maxDmlTimeMs: int = 0


# ============================================================================
# 解析器类
# ============================================================================

class FLUXWMSLogParser:
    """FLUX WMS 日志解析器"""

    def __init__(self):
        self.sql_queries: List[SQLQuery] = []
        self.dml_statements: List[DMLStatement] = []
        self.pre_post_operations: List[PrePostOperation] = []
        self.phase_starts: List[PhaseStart] = []
        self.pre_post_events: List[PrePostEvent] = []
        self.sp_calls: List[SPCall] = []
        self.sp_call_map: Dict[str, SPCall] = {}  # 临时映射，用于匹配 start/end
        self.exceptions: List[ExceptionInfo] = []
        self.wco_params: List[WCOParam] = []
        self.service_steps: List[ServiceStep] = []  # 自定义服务步骤
        self.service_step_map: Dict[int, ServiceStep] = {}  # 临时映射，用于匹配 start/end
        self.login_info: LoginInfo = LoginInfo()
        self.biz_data: BizData = BizData()
        self.unrecognized_lines: List[Dict[str, str]] = []
        self.statistics: Statistics = Statistics()
        self.users: set = set()
        self.time_range: Dict[str, str] = {}
        self.first_timestamp: Optional[str] = None
        self.last_timestamp: Optional[str] = None
        self._collecting_stacktrace: bool = False
        self._stacktrace_lines: List[str] = []
        self._pending_error_code: Optional[str] = None
        self._pending_error_msg: Optional[str] = None
        self._pending_sp_name: Optional[str] = None
        self._pending_pre_post_exc: Optional[str] = None
        self._current_event: Optional[PrePostEvent] = None  # 当前正在处理的事件
        self._pending_sp_calls: List[Dict] = []  # 暂存的 SP 调用信息
        self._active_step_nos: Set[int] = set()  # 当前活跃的自定义服务步骤编号
        self._pending_param_sql: Optional[DMLStatement] = None  # 待匹配参数数组的前一条 DML（含 ? 占位符）

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """
        解析日志文件

        Args:
            file_path: 日志文件路径

        Returns:
            解析结果字典
        """
        self.statistics.totalLines = 0

        # 尝试不同编码读取文件
        lines = None
        for encoding in ['utf-8', 'gbk', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue

        if lines is None:
            raise ValueError(f"无法读取文件: {file_path}")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            self.statistics.totalLines += 1
            self._parse_line(line, line_num)

        # 结束可能未关闭的堆栈收集
        self._finish_stacktrace()

        # 计算统计数据
        self._calculate_statistics()

        # 构建返回结果
        return self._build_result(file_path)

    def _parse_line(self, line: str, line_num: int) -> None:
        """解析单行日志"""
        # 尝试匹配日志行格式
        match = LOG_LINE_PATTERN.match(line)
        if not match:
            # 如果正在收集堆栈，将该行作为堆栈续行
            if self._collecting_stacktrace:
                self._stacktrace_lines.append(line)
                # 检查是否是 Caused by 行
                caused_match = CAUSED_BY_PATTERN.search(line)
                if caused_match and self.exceptions:
                    last_exc = self.exceptions[-1]
                    last_exc.causedBy = caused_match.group(1)
                    last_exc.causedByMessage = caused_match.group(2)
                    chain_item = caused_match.group(1)
                    if caused_match.group(2):
                        chain_item += ': ' + caused_match.group(2)
                    last_exc.causedByChain.append(chain_item)
                return
            self.unrecognized_lines.append({
                'line_number': line_num,
                'content': line
            })
            return

        # 如果正在收集堆栈且当前行匹配日志格式，结束堆栈收集
        if self._collecting_stacktrace:
            self._finish_stacktrace()

        timestamp, user, content = match.groups()

        # 记录用户
        self.users.add(user)

        # 更新时间范围
        self._update_time_range(timestamp)

        # 解析器列表，按优先级排序
        parsers = [
            self._try_parse_sql_query,
            self._try_parse_dml_statement,
            self._try_parse_dml_with_params,       # 新增：带 ? 占位符的 DML
            self._try_parse_pre_post_operation,
            self._try_parse_phase_result,
            self._try_parse_phase_start,
            self._try_parse_ext_params,
            self._try_parse_sp_invoke,
            self._try_parse_sp_call,
            self._try_parse_sp_exec,
            self._try_parse_service_step,
            self._try_parse_exception,
            self._try_parse_wco_param,
            self._try_parse_sql_params_array,       # 新增：JSON 参数数组（需在最后，捕获未匹配的行）
        ]

        parsed = False
        for parser_func in parsers:
            if parser_func(timestamp, user, content, line_num):
                parsed = True
                break

        # 收集到活跃的自定义服务步骤 details 中（无论该行是否被其他解析器匹配）
        self._collect_service_step_details(timestamp, user, content, line_num)

        # 未识别的内容
        if not parsed and content.strip():
            self.unrecognized_lines.append({
                'line_number': line_num,
                'timestamp': timestamp,
                'user': user,
                'content': content
            })

    def _update_time_range(self, timestamp: str) -> None:
        """更新时间范围"""
        if self.first_timestamp is None or timestamp < self.first_timestamp:
            self.first_timestamp = timestamp
        if self.last_timestamp is None or timestamp > self.last_timestamp:
            self.last_timestamp = timestamp

    def _try_parse_sql_query(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析 SQL 查询"""
        match = SQL_QUERY_PATTERN.match(content)
        if match:
            result_count, used_time, sql = match.groups()
            query = SQLQuery(
                timestamp=timestamp,
                user=user,
                resultCount=int(result_count),
                usedTimeMs=int(used_time),
                sql=sql,
                isSlowQuery=int(used_time) >= SLOW_QUERY_THRESHOLD_MS,
                line=line_num
            )
            self.sql_queries.append(query)
            return True
        return False

    def _try_parse_dml_statement(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析 DML 语句"""
        match = DML_PATTERN.match(content)
        if match:
            affected_rows, used_time, sql = match.groups()
            dml = DMLStatement(
                timestamp=timestamp,
                user=user,
                affectedRows=int(affected_rows),
                usedTimeMs=int(used_time),
                sql=sql,
                line=line_num
            )
            self.dml_statements.append(dml)
            return True
        return False

    def _try_parse_dml_with_params(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """
        尝试解析带参数占位符的 DML 语句
        格式: [N] (usedTime:N) SQL（含 ? 占位符），下一行是 JSON 参数数组
        """
        match = DML_PARAM_PATTERN.match(content.strip())
        if match:
            affected_rows, used_time, sql = match.groups()
            dml = DMLStatement(
                timestamp=timestamp,
                user=user,
                affectedRows=int(affected_rows),
                usedTimeMs=int(used_time),
                sql=sql,
                line=line_num
            )
            # 如果 SQL 含 ? 占位符，设置 pending 等待下一行的参数数组
            if '?' in sql:
                self._pending_param_sql = dml
            self.dml_statements.append(dml)
            return True
        return False

    def _try_parse_sql_params_array(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """
        尝试解析 JSON 参数数组（紧跟在含 ? 的 DML 之后）
        """
        # 没有待匹配的 DML，直接返回 False
        if self._pending_param_sql is None:
            return False

        stripped = content.strip()
        if stripped.startswith('['):
            try:
                # 校验是合法 JSON
                json.loads(stripped)
                self._pending_param_sql.params = stripped
                self._pending_param_sql = None
                return True
            except (json.JSONDecodeError, ValueError):
                pass

        # 非参数数组行，清除 pending 但返回 False（让其他解析器继续处理）
        self._pending_param_sql = None
        return False

    def _try_parse_pre_post_operation(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析前后置操作 - 创建新的 PrePostEvent"""
        match = PRE_POST_PATTERN.match(content)
        if match:
            phase, scope, module, action = match.groups()

            # 构建事件类型
            if phase == '前置':
                if scope == '外':
                    event_type = '前置事务外'
                else:
                    event_type = '前置事务内'
            else:
                if scope == '外':
                    event_type = '后置事务外'
                else:
                    event_type = '后置事务内'

            # 保存当前事件
            event = PrePostEvent(
                timestamp=timestamp,
                user=user,
                eventType=event_type,
                functionId=module,
                actionCode=action,
                line=line_num
            )

            # 附加暂存的 SP 调用信息
            if self._pending_sp_calls:
                event.spCalls = self._pending_sp_calls.copy()
                self._pending_sp_calls = []

            # 检查内容中是否包含 SP 事务内调用信息（可能有多个）
            sp_invoke_matches = list(SP_INVOKE_PATTERN.finditer(content))
            for sp_invoke_match in sp_invoke_matches:
                invoke_type = sp_invoke_match.group(1)
                invoke_data = sp_invoke_match.group(2)
                if invoke_type == '参数信息':
                    event.spInvokeParams = invoke_data
                else:
                    event.spInvokeResult = invoke_data

            self.pre_post_events.append(event)
            self._current_event = event

            # 同时保存到 pre_post_operations
            operation = PrePostOperation(
                timestamp=timestamp,
                user=user,
                phase=phase,
                scope=scope,
                module=module,
                action=action,
                line=line_num
            )
            self.pre_post_operations.append(operation)
            return True
        return False

    def _try_parse_phase_result(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析前后置成功/失败状态 - 创建新的 PrePostEvent"""
        match = PHASE_RESULT_PATTERN.match(content)
        if match:
            phase, scope, result, result_detail, function_id, action_code = match.groups()

            # 构建事件类型：前置成功、前置_IN成功、后置成功、后置_IN成功
            event_type = f'{phase}{scope or ""}{result}'

            # 创建新的 PrePostEvent
            event = PrePostEvent(
                timestamp=timestamp,
                user=user,
                eventType=event_type,
                functionId=function_id,
                actionCode=action_code,
                line=line_num
            )

            # 附加暂存的 SP 调用信息
            if self._pending_sp_calls:
                event.spCalls = self._pending_sp_calls.copy()
                self._pending_sp_calls = []

            self.pre_post_events.append(event)
            self._current_event = event

            # 同时保存到 phase_starts
            phase_start = PhaseStart(
                timestamp=timestamp,
                user=user,
                phaseType=f'{phase}{scope or ""}{result}',
                functionId=function_id,
                actionCode=action_code,
                result=result,
                resultDetail=result_detail,
                line=line_num
            )
            self.phase_starts.append(phase_start)
            return True
        return False

    def _try_parse_ext_params(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析扩展操作传参数据 - 附加到当前事件"""
        match = EXT_PARAMS_PATTERN.search(content)
        if match:
            params = match.group(1)
            # 附加到当前事件
            if self._current_event:
                self._current_event.extParams = params
            # 同时更新 pre_post_operations
            if self.pre_post_operations:
                last_op = self.pre_post_operations[-1]
                last_op.params = params
            return True
        return False

    def _try_parse_sp_invoke(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析 SP 事务内调用信息 - 附加到当前事件"""
        match = SP_INVOKE_PATTERN.search(content)
        if match:
            invoke_type = match.group(1)  # 参数信息 或 返回信息
            invoke_data = match.group(2)
            # 附加到当前事件
            if self._current_event:
                if invoke_type == '参数信息':
                    self._current_event.spInvokeParams = invoke_data
                else:
                    self._current_event.spInvokeResult = invoke_data
            # 同时更新 pre_post_operations
            if self.pre_post_operations:
                last_op = self.pre_post_operations[-1]
                if last_op.spResult:
                    last_op.spResult += f'\n{invoke_type}: {invoke_data}'
                else:
                    last_op.spResult = f'{invoke_type}: {invoke_data}'
            return True
        return False

    def _try_parse_phase_start(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析前后置开始 - 创建 PrePostEvent"""
        match = PHASE_START_PATTERN.match(content)
        if match:
            phase_type, function_id, action_code = match.groups()

            # 构建事件类型
            if '前置' in phase_type:
                if '_IN' in phase_type:
                    event_type = '前置_IN开始'
                else:
                    event_type = '前置开始'
            else:
                if '_IN' in phase_type:
                    event_type = '后置_IN开始'
                else:
                    event_type = '后置开始'

            # 创建 PrePostEvent
            event = PrePostEvent(
                timestamp=timestamp,
                user=user,
                eventType=event_type,
                functionId=function_id,
                actionCode=action_code,
                line=line_num
            )

            # 附加暂存的 SP 调用信息
            if self._pending_sp_calls:
                event.spCalls = self._pending_sp_calls.copy()
                self._pending_sp_calls = []

            self.pre_post_events.append(event)
            self._current_event = event

            # 同时保存到 phase_starts
            phase_start = PhaseStart(
                timestamp=timestamp,
                user=user,
                phaseType=phase_type,
                functionId=function_id,
                actionCode=action_code,
                line=line_num
            )
            self.phase_starts.append(phase_start)
            return True
        return False

    def _try_parse_sp_call(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析 SP 调用开始/结束 - 附加到当前事件"""
        # 检查 START excute SP
        start_match = SP_START_PATTERN.match(content)
        if start_match:
            sp_timestamp, sp_name = start_match.groups()
            sp_call = SPCall(spName=sp_name, startTime=sp_timestamp, line=line_num)
            self.sp_calls.append(sp_call)
            self.sp_call_map[sp_name] = sp_call

            # 附加到当前事件
            if self._current_event:
                self._current_event.spCalls.append({
                    'spName': sp_name,
                    'startTime': sp_timestamp,
                    'line': line_num
                })
            return True

        # 检查 END excute SP
        end_match = SP_END_PATTERN.match(content)
        if end_match:
            sp_timestamp, sp_name = end_match.groups()
            if sp_name in self.sp_call_map:
                self.sp_call_map[sp_name].endTime = sp_timestamp
                # 更新当前事件中的 SP 调用信息
                if self._current_event:
                    for sp in self._current_event.spCalls:
                        if sp.get('spName') == sp_name:
                            sp['endTime'] = sp_timestamp
                            break
            else:
                sp_call = SPCall(spName=sp_name, endTime=sp_timestamp, line=line_num)
                self.sp_calls.append(sp_call)
            return True

        return False

    def _try_parse_sp_exec(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析 SP 执行结果 - 分离入参和出参"""
        match = SP_EXEC_PATTERN.search(content)
        if match:
            sp_name, exec_sql, result = match.groups()
            if sp_name not in self.sp_call_map:
                sp_call = SPCall(spName=sp_name)
                self.sp_calls.append(sp_call)
                self.sp_call_map[sp_name] = sp_call
            self.sp_call_map[sp_name].executionSql = exec_sql.strip()
            self.sp_call_map[sp_name].result = result

            # 尝试从执行 SQL 中提取 usedTime
            time_match = re.search(r'\(usedTime:(\d+)\)', exec_sql)
            if time_match:
                self.sp_call_map[sp_name].usedTimeMs = int(time_match.group(1))

            # 解析入参
            input_params = exec_sql.strip()

            sp_call_info = {
                'spName': sp_name,
                'inputParams': input_params,
                'outputResult': result,
                'usedTime': self.sp_call_map[sp_name].usedTimeMs,
                'line': line_num
            }

            # 附加到当前事件或暂存
            if self._current_event:
                self._current_event.spCalls.append(sp_call_info)
            else:
                self._pending_sp_calls.append(sp_call_info)

            # 检查结果是否包含错误码 (格式: 错误码#消息)
            if result:
                error_match = re.match(r'(\d+)#(.+)', result)
                if error_match:
                    error_code = error_match.group(1)
                    error_msg = error_match.group(2)
                    # 创建异常记录
                    exception = ExceptionInfo(
                        timestamp=timestamp,
                        user=user,
                        exceptionType='SPExecutionError',
                        message=f'SP {sp_name} 执行返回错误: {error_code}#{error_msg}',
                        errorCode=error_code,
                        errorMessage=error_msg,
                        line=line_num
                    )
                    self.exceptions.append(exception)

            return True
        return False

    def _try_parse_exception(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析异常"""
        # 检查错误码模式: 0X~错误码~错误消息~标志
        error_code_match = ERROR_CODE_PATTERN.match(content.strip())
        if error_code_match:
            error_code = error_code_match.group(1)
            error_msg = error_code_match.group(2)
            # 始终暂存错误码，等待后续异常使用
            self._pending_error_code = error_code
            self._pending_error_msg = error_msg
            return True

        # 检查 SP 执行错误: 执行SP:名称 ... 结果:{{错误码#消息}}
        # 只暂存信息，不创建异常（等待最终的 Java 异常合并）
        sp_error_match = SP_EXEC_ERROR_PATTERN.search(content)
        if sp_error_match:
            sp_name = sp_error_match.group(1)
            error_code = sp_error_match.group(2)
            error_msg = sp_error_match.group(3)

            # 暂存 SP 错误信息
            self._pending_sp_name = sp_name
            self._pending_error_code = error_code
            self._pending_error_msg = error_msg

            return True

        # 检查前置事务执行异常: (前置_IN执行异常)扩展操作:功能模块,动作代码
        # 只暂存信息，不创建异常（等待最终的 Java 异常合并）
        pre_post_exc_match = PRE_POST_EXCEPTION_PATTERN.search(content)
        if pre_post_exc_match:
            phase = pre_post_exc_match.group(1)
            scope = pre_post_exc_match.group(2) or ''
            module = pre_post_exc_match.group(3)
            action = pre_post_exc_match.group(4)

            # 暂存前置事务异常信息
            self._pending_pre_post_exc = f'{phase}{scope}执行异常: {module}.{action}'

            return True

        # 检查 Exception 或 Error
        exc_match = EXCEPTION_PATTERN.search(content)
        if exc_match:
            exc_message = exc_match.group(1)

            # 构建消息：合并所有暂存信息
            message_parts = []
            if self._pending_sp_name:
                message_parts.append(f'SP {self._pending_sp_name} 执行返回错误')
            if self._pending_pre_post_exc:
                message_parts.append(self._pending_pre_post_exc)
            if exc_message:
                message_parts.append(exc_message)
            elif self._pending_error_msg:
                message_parts.append(self._pending_error_msg)

            exception = ExceptionInfo(
                timestamp=timestamp,
                user=user,
                exceptionType=self._extract_exception_type(content),
                message=': '.join(message_parts) if message_parts else exc_message,
                line=line_num
            )

            # 附加暂存的错误码
            if self._pending_error_code:
                exception.errorCode = self._pending_error_code
                exception.errorMessage = self._pending_error_msg
                self._pending_error_code = None
                self._pending_error_msg = None

            # 清空暂存的 SP 名称和前置事务异常信息
            self._pending_sp_name = None
            self._pending_pre_post_exc = None

            # 检查 Caused by
            caused_match = CAUSED_BY_PATTERN.search(content)
            if caused_match:
                exception.causedBy = caused_match.group(1)
                exception.causedByMessage = caused_match.group(2)
                chain_item = caused_match.group(1)
                if caused_match.group(2):
                    chain_item += ': ' + caused_match.group(2)
                exception.causedByChain.append(chain_item)

            self.exceptions.append(exception)

            # 开始收集堆栈信息
            self._collecting_stacktrace = True
            self._stacktrace_lines = [content]

            return True

        # 检查 Caused by（单独出现）
        caused_match = CAUSED_BY_PATTERN.search(content)
        if caused_match:
            # 如果已经有异常记录，更新最后一条
            if self.exceptions:
                last_exc = self.exceptions[-1]
                last_exc.causedBy = caused_match.group(1)
                last_exc.causedByMessage = caused_match.group(2)
                chain_item = caused_match.group(1)
                if caused_match.group(2):
                    chain_item += ': ' + caused_match.group(2)
                last_exc.causedByChain.append(chain_item)
            return True

        return False

    def _finish_stacktrace(self) -> None:
        """结束堆栈收集，将堆栈信息保存到最后一个异常"""
        if self._collecting_stacktrace and self.exceptions:
            last_exc = self.exceptions[-1]
            if self._stacktrace_lines:
                last_exc.fullStack = '\n'.join(self._stacktrace_lines)
            self._collecting_stacktrace = False
            self._stacktrace_lines = []

    def _extract_exception_type(self, content: str) -> str:
        """提取异常类型"""
        type_match = re.search(r'([\w.]+(?:Exception|Error))', content)
        if type_match:
            return type_match.group(1)

        return 'Exception' if 'Exception' in content else ('Error' if 'Error' in content else 'Unknown')

    def _try_parse_service_step(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析自定义服务步骤"""
        # 检查步骤开始
        start_match = SERVICE_STEP_START_PATTERN.search(content)
        if start_match:
            step_no = int(start_match.group(1))
            logic_model = start_match.group(2)

            # 创建新的服务步骤（details 留空，由 _collect_service_step_details 收集所有中间行）
            if step_no not in self.service_step_map:
                step = ServiceStep(
                    stepNo=step_no,
                    logicModel=logic_model,
                    startTime=timestamp,
                    timestamp=timestamp,
                    user=user,
                    line=line_num
                )
                self.service_steps.append(step)
                self.service_step_map[step_no] = step

            self._active_step_nos.add(step_no)
            return True

        # 检查步骤结束
        end_match = SERVICE_STEP_END_PATTERN.search(content)
        if end_match:
            result = end_match.group(1)
            step_no = int(end_match.group(2))
            logic_model = end_match.group(3)

            # 先从活跃集合移除，后续 _collect_service_step_details 不会再追加此行
            self._active_step_nos.discard(step_no)

            if step_no in self.service_step_map:
                step = self.service_step_map[step_no]
                step.endTime = timestamp
                step.result = result
            else:
                # 只有结束信息，没有开始（异常情况）
                step = ServiceStep(
                    stepNo=step_no,
                    logicModel=logic_model,
                    endTime=timestamp,
                    result=result,
                    timestamp=timestamp,
                    user=user,
                    line=line_num
                )
                self.service_steps.append(step)
                self.service_step_map[step_no] = step

            return True

        return False

    def _collect_service_step_details(self, timestamp: str, user: str, content: str, line_num: int = 0) -> None:
        """
        将当前日志行追加到所有活跃的自定义服务步骤的 details 中。
        确保 start 到 end 之间的每一行都被完整记录。
        """
        if not self._active_step_nos:
            return
        for step_no in self._active_step_nos:
            step = self.service_step_map.get(step_no)
            if step:
                if step.details:
                    step.details += f'\n{content}'
                else:
                    step.details = content

    def _try_parse_wco_param(self, timestamp: str, user: str, content: str, line_num: int = 0) -> bool:
        """尝试解析 WCO 参数"""
        match = WCO_PATTERN.match(content)
        if match:
            param_name, param_value, filter_conditions, match_result, default_value = match.groups()
            wco = WCOParam(
                timestamp=timestamp,
                user=user,
                paramName=param_name,
                paramValue=param_value,
                filterConditions=filter_conditions,
                matchResult=match_result,
                defaultValue=default_value,
                line=line_num
            )
            self.wco_params.append(wco)
            return True
        return False

    def _calculate_statistics(self) -> None:
        """计算统计数据"""
        self.statistics.sqlQueryCount = len(self.sql_queries)
        self.statistics.dmlStatementCount = len(self.dml_statements)
        self.statistics.spCallCount = len(self.sp_calls)
        self.statistics.exceptionCount = len(self.exceptions)
        self.statistics.wcoParamCount = len(self.wco_params)
        self.statistics.prePostOperationCount = len(self.pre_post_operations)

        # 慢查询统计
        self.statistics.slowQueryCount = sum(1 for q in self.sql_queries if q.isSlowQuery)

        # SQL 查询时间统计
        if self.sql_queries:
            sql_times = [q.usedTimeMs for q in self.sql_queries]
            self.statistics.totalSqlTimeMs = sum(sql_times)
            self.statistics.avgSqlTimeMs = self.statistics.totalSqlTimeMs / len(sql_times)
            self.statistics.maxSqlTimeMs = max(sql_times)

        # DML 语句时间统计
        if self.dml_statements:
            dml_times = [d.usedTimeMs for d in self.dml_statements]
            self.statistics.totalDmlTimeMs = sum(dml_times)
            self.statistics.avgDmlTimeMs = self.statistics.totalDmlTimeMs / len(dml_times)
            self.statistics.maxDmlTimeMs = max(dml_times)

    def _build_result(self, file_path: str) -> Dict[str, Any]:
        """构建返回结果"""
        # 从日志内容中提取登录信息
        self._extract_login_info()

        return {
            'metadata': {
                'fileName': Path(file_path).name,
                'totalLines': self.statistics.totalLines,
                'timeRange': {
                    'start': self.first_timestamp or '',
                    'end': self.last_timestamp or ''
                },
                'users': list(self.users),
                'warehouseId': self.login_info.warehouseId or '',
                'organizationId': self.login_info.organizationId or ''
            },
            'sqlQueries': [asdict(q) for q in self.sql_queries],
            'dmlStatements': [asdict(d) for d in self.dml_statements],
            'prePostOperations': [asdict(p) for p in self.pre_post_operations],
            'phaseStarts': [asdict(ps) for ps in self.phase_starts],
            'prePostEvents': [asdict(evt) for evt in self.pre_post_events],
            'spCalls': [asdict(sp) for sp in self.sp_calls],
            'exceptions': [asdict(e) for e in self.exceptions],
            'wcoParams': [asdict(w) for w in self.wco_params],
            'serviceSteps': [asdict(s) for s in self.service_steps],
            'loginInfo': asdict(self.login_info),
            'bizData': asdict(self.biz_data),
            'unrecognizedLines': self.unrecognized_lines,
            'statistics': asdict(self.statistics)
        }

    def _extract_login_info(self) -> None:
        """从解析结果中提取登录信息"""
        # 从 SQL 查询中提取 warehouseId 和 organizationId
        for query in self.sql_queries:
            # 提取 organizationId
            org_match = re.search(r"organizationId\s*=\s*'(\w+)'", query.sql)
            if org_match and not self.login_info.organizationId:
                self.login_info.organizationId = org_match.group(1)

            # 提取 warehouseId
            wh_match = re.search(r"warehouseId\s*=\s*'(\w+)'", query.sql)
            if wh_match and not self.login_info.warehouseId:
                self.login_info.warehouseId = wh_match.group(1)

        # 从第一个用户设置 userId
        if self.users:
            self.login_info.userId = next(iter(self.users))

        # 从 SP 调用中提取 documentNo（如果有）
        for sp in self.sp_calls:
            if sp.executionSql:
                doc_match = re.search(r"'(\w+)'", sp.executionSql)
                if doc_match:
                    self.biz_data.documentNo = doc_match.group(1)
                    break


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='FLUX WMS 日志解析器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python parser.py log/Untitled-1.log
  python parser.py log/Untitled-1.log --output result.json
  python parser.py log/Untitled-1.log --output result.json --pretty
        '''
    )

    parser.add_argument(
        'log_file',
        help='日志文件路径'
    )

    parser.add_argument(
        '--output', '-o',
        help='JSON 输出文件路径（不指定则输出到标准输出）'
    )

    parser.add_argument(
        '--pretty', '-p',
        action='store_true',
        help='格式化 JSON 输出'
    )

    args = parser.parse_args()

    # 检查文件是否存在
    if not Path(args.log_file).exists():
        print(f"错误: 文件不存在 - {args.log_file}", file=sys.stderr)
        sys.exit(1)

    # 解析日志
    log_parser = FLUXWMSLogParser()
    result = log_parser.parse_file(args.log_file)

    # 输出结果
    indent = 2 if args.pretty else None
    json_str = json.dumps(result, ensure_ascii=False, indent=indent)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f"解析结果已保存到: {args.output}")
    else:
        print(json_str)


if __name__ == '__main__':
    main()
