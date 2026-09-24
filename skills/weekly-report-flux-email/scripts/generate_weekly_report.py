#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目周报处理工具
功能：
  1. 将 PPTX 项目周报导出为 PDF（依赖 PowerPoint COM 自动化）
  2. 从 PPTX 中动态识别"本周计划完成情况"和"下周工作计划"页面，提取表格数据
  3. 根据提取的数据生成邮件 HTML 正文
作者：SUNC
"""

import os
import sys
import re
import argparse
from pathlib import Path

# ============================================================
# 工具函数
# ============================================================

def _split_text(text: str) -> list:
    """按通用分隔符拆分文本（处理 \\n、\\x0b、\\r 等）"""
    return re.split(r'[\n\x0b\r]+', text)


def _clean_cell_text(text: str) -> str:
    """清理单元格文本：去除首尾空白，合并换行（处理多种换行符）"""
    return ' '.join(_split_text(text.strip())).strip()


def _format_date(text: str) -> str:
    """将日期从 M/D 格式转换为 M月D日 格式，支持范围如 6/4-6/6 → 6月4日-6月6日"""
    # 范围格式: M/D-M/D
    m = re.match(r'^(\d{1,2})/(\d{1,2})\s*[-–~]\s*(\d{1,2})/(\d{1,2})$', text)
    if m:
        return f'{m.group(1)}月{m.group(2)}日-{m.group(3)}月{m.group(4)}日'
    # 同月范围: M/D-D
    m = re.match(r'^(\d{1,2})/(\d{1,2})\s*[-–~]\s*(\d{1,2})$', text)
    if m:
        return f'{m.group(1)}月{m.group(2)}日-{m.group(1)}月{m.group(3)}日'
    # 单日期: M/D
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', text)
    if m:
        return f'{m.group(1)}月{m.group(2)}日'
    return text


# ============================================================
# 模块 1: PPTX → PDF 转换（基于 PowerPoint COM 自动化）
# ============================================================

def pptx_to_pdf(pptx_path: str, pdf_path: str = None) -> str:
    """
    将 PPTX 文件导出为 PDF。
    依赖：Windows + PowerPoint 已安装 + pywin32
    返回：生成的 PDF 文件路径
    """
    if pdf_path is None:
        pdf_path = str(Path(pptx_path).with_suffix('.pdf'))

    # 如果 PDF 已存在且比 PPTX 新，跳过
    if os.path.exists(pdf_path):
        pptx_mtime = os.path.getmtime(pptx_path)
        pdf_mtime = os.path.getmtime(pdf_path)
        if pdf_mtime >= pptx_mtime:
            print(f"[跳过] PDF 已是最新: {pdf_path}")
            return pdf_path

    import win32com.client

    powerpoint = None
    presentation = None
    try:
        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        # 部分环境不允许隐藏窗口，先尝试隐藏，失败则保持可见
        try:
            powerpoint.Visible = 0
        except Exception:
            pass

        abs_pptx = os.path.abspath(pptx_path)
        abs_pdf = os.path.abspath(pdf_path)

        print(f"[转换] {os.path.basename(pptx_path)} → PDF ...")
        presentation = powerpoint.Presentations.Open(abs_pptx, WithWindow=0)

        # 32 = ppSaveAsPDF
        presentation.SaveAs(abs_pdf, 32)

        print(f"[完成] PDF 已保存至: {pdf_path}")
        return pdf_path

    except Exception as e:
        print(f"[错误] PPTX → PDF 转换失败: {e}")
        raise
    finally:
        if presentation:
            presentation.Close()
        if powerpoint:
            powerpoint.Quit()


# ============================================================
# 模块 2: 动态幻灯片识别 & 表格数据提取
# ============================================================

# 用于匹配幻灯片标题的关键词
TITLE_KEYWORDS = {
    'this_week': ['本周计划完成情况', '本周工作计划', '本周计划'],
    'next_week': ['下周工作计划', '下周计划'],
}


def _find_slide_by_title(slides, keywords: list) -> object:
    """
    根据标题关键词动态查找幻灯片。
    遍历所有幻灯片，查找标题文本中包含任一关键词的幻灯片。
    返回第一个匹配的幻灯片对象，找不到返回 None。
    """
    for slide in slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                for kw in keywords:
                    if kw in text:
                        return slide
    return None


def extract_week_number(pptx_path: str, prs=None) -> str:
    """从幻灯片标题中提取周数，如 '2026 WK22'。可复用已打开的 Presentation 对象。"""
    try:
        if prs is None:
            from pptx import Presentation
            prs = Presentation(pptx_path)
        if prs.slides:
            slide1 = prs.slides[0]
            for shape in slide1.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text
                    m = re.search(r'\d{4}\s*WK(\d+)', text)
                    if m:
                        return f"WK{m.group(1)}"
        return "???"
    except Exception:
        return "???"


def extract_project_name(pptx_path: str, prs=None) -> str:
    """从第一张幻灯片的标题文本中提取项目名称。
    策略：取第一行非空文本，去除常见的"周报"/"项目周报"等后缀。
    可复用已打开的 Presentation 对象。
    """
    try:
        if prs is None:
            from pptx import Presentation
            prs = Presentation(pptx_path)
        if prs.slides:
            for shape in prs.slides[0].shapes:
                if not shape.has_text_frame:
                    continue
                first_line = _split_text(shape.text_frame.text)[0].strip()
                first_line = re.sub(r'(项目)?周报(汇报)?$', '', first_line).strip()
                if first_line:
                    return first_line
        return "项目"
    except Exception:
        return "项目"


def _detect_column_mapping(header_cells: list) -> dict:
    """
    根据表头文本识别列映射。
    返回 {列类型: 列索引}
    """
    mapping = {}
    for i, h in enumerate(header_cells):
        h_clean = h.strip()
        if h_clean == '序号':
            mapping['序号'] = i
        elif h_clean == '阶段':
            mapping['阶段'] = i
        elif '任务' in h_clean or '描述' in h_clean or '计划' in h_clean:
            mapping['任务描述'] = i
        elif h_clean == '时间':
            mapping['时间'] = i
        elif h_clean == '状态' or '进度' in h_clean:
            mapping['状态'] = i
    return mapping


def _extract_table_from_slide(slide, include_status: bool = True) -> list:
    """
    从指定幻灯片中提取表格数据。

    参数:
        slide: pptx Slide 对象
        include_status: 是否包含"状态"列（本周表格有，下周表格没有）

    返回 list of dict
    """
    rows_data = []
    for shape in slide.shapes:
        if shape.has_table:
            table = shape.table
            # 跳过过小的表（如时间线表），数据表至少 2 行 × 4 列（表头+1行数据）
            if len(table.rows) < 2 or len(table.columns) < 4:
                continue

            header_cells = [_clean_cell_text(c.text) for c in table.rows[0].cells]
            col_map = _detect_column_mapping(header_cells)

            if '序号' not in col_map or '阶段' not in col_map or '任务描述' not in col_map:
                continue  # 不匹配的表格

            col_seq = col_map['序号']
            col_phase = col_map['阶段']
            col_task = col_map['任务描述']
            col_time = col_map.get('时间', -1)
            col_status = col_map.get('状态', -1)

            for ri in range(1, len(table.rows)):
                row = table.rows[ri]
                cells = [_clean_cell_text(c.text) for c in row.cells]
                seq = cells[col_seq] if col_seq < len(cells) else ''
                if not seq or not seq.isdigit():
                    continue  # 跳过空行或非数据行

                row_dict = {
                    '序号': seq,
                    '阶段': cells[col_phase] if col_phase < len(cells) else '',
                    '任务描述': cells[col_task] if col_task < len(cells) else '',
                    '时间': _format_date(cells[col_time]) if 0 <= col_time < len(cells) else '',
                }
                if include_status:
                    row_dict['状态'] = cells[col_status] if 0 <= col_status < len(cells) else ''

                rows_data.append(row_dict)
            break  # 每个幻灯片只取一个主表格
    return rows_data


def extract_all_data(pptx_path: str) -> dict:
    """
    从 PPTX 文件中动态提取所有需要的数据。

    动态查找逻辑：
      - 根据标题关键词匹配"本周计划完成情况"所在幻灯片
      - 根据标题关键词匹配"下周工作计划"所在幻灯片
      - 页数不固定，完全由标题内容决定

    返回: {
        'project_name': str,
        'week_number': str,
        'this_week_rows': list,
        'next_week_rows': list,
    }
    """
    from pptx import Presentation

    prs = Presentation(pptx_path)
    project_name = extract_project_name(pptx_path, prs=prs)
    week_number = extract_week_number(pptx_path, prs=prs)

    # 动态查找幻灯片
    this_week_slide = _find_slide_by_title(prs.slides, TITLE_KEYWORDS['this_week'])
    next_week_slide = _find_slide_by_title(prs.slides, TITLE_KEYWORDS['next_week'])

    this_week_rows = []
    next_week_rows = []

    if this_week_slide:
        this_week_rows = _extract_table_from_slide(this_week_slide, include_status=True)
    else:
        print("[警告] 未找到「本周计划完成情况」页面")

    if next_week_slide:
        next_week_rows = _extract_table_from_slide(next_week_slide, include_status=False)
    else:
        print("[警告] 未找到「下周工作计划」页面")

    return {
        'project_name': project_name,
        'week_number': week_number,
        'this_week_rows': this_week_rows,
        'next_week_rows': next_week_rows,
    }


# ============================================================
# 模块 3: 邮件 HTML 生成
# ============================================================

def generate_email_html(data: dict) -> str:
    """
    根据提取的数据生成邮件 HTML 内容。
    格式与参考文件保持一致：表格颜色 #B40000、字体 微软雅黑、宽度 566pt。
    """
    project_name = data['project_name']
    week_number = data['week_number']
    week_num = week_number.replace('WK', '')

    parts = []

    # --- 开篇问候 ---
    parts.append('<div><font>')
    parts.append('<div style="font-family: 微软雅黑">Dear All：</div>')
    parts.append(
        f'<div style=""><font face="微软雅黑" style="">&nbsp; &nbsp; &nbsp; '
        f'以下是{project_name}第{week_num}周的周报。详细的汇报内容已附在邮件的附件中，请各位领导审阅斧正。</font>'
    )
    parts.append('</div>')
    parts.append('<div><br></div><div style="">')
    parts.append('</div>')

    # --- 本周计划完成情况 ---
    parts.append('<div>')
    parts.append('<span style="font-family: 微软雅黑">&nbsp; &nbsp; &nbsp;</span>')
    parts.append('<b>本周计划完成情况：</b></div><div><b>')
    parts.append(_build_table(data['this_week_rows'], _THIS_WEEK_COLS))
    parts.append('</b></div><div><b><br></b></div>')
    parts.append('</font>')
    parts.append('</div>')

    # --- 下周工作计划 ---
    parts.append('<div></div>')
    parts.append('<div><font>')
    parts.append('<span style="font-family: &quot;lucida Grande&quot;, Verdana;">&nbsp; &nbsp; &nbsp;</span>')
    parts.append('<b>下周工作计划：</b></font></div><div><font><b>')
    parts.append(_build_table(data['next_week_rows'], _NEXT_WEEK_COLS))
    parts.append('<br></b></font></div>')

    # --- 签名 ---
    parts.append('<div><br></div>')
    parts.append(_build_signature())

    # --- 收尾 ---
    parts.append('<div>&nbsp;</div>')
    parts.append('<div><tincludetail><!--&lt;![endif]--></tincludetail></div>')
    parts.append('<!--&lt;![endif]--><!--&lt;![endif]--><!--&lt;![endif]--><!--&lt;![endif]-->'
                 '<!--&lt;![endif]--><!--&lt;![endif]--><!--&lt;![endif]--><!--&lt;![endif]-->')

    return '\n'.join(parts)


def _build_table(rows: list, columns: list) -> str:
    """
    通用 HTML 表格构建。

    参数:
        rows: list of dict — 表格数据
        columns: list of tuple — (字段名, 表头文字, 列宽, 对齐方式)
                 例如 [('序号','序号','65pt','center'), ('任务描述','任务描述','306pt','left')]
    """
    if not rows:
        return '<p style="font-family:微软雅黑;">（暂无数据）</p>'

    lines = []
    lines.append('<table border="0" cellpadding="0" cellspacing="0" '
                 'style="border-collapse:collapse;width:545pt" width="727"><colgroup>')
    for _, _, width, _ in columns:
        w_val = width.replace('pt', '')
        lines.append(f'<col style="mso-ruby-visibility:none;mso-width-source:userset;'
                     f'mso-width-alt:10581;width:{width};" width="{w_val}">')
    lines.append('</colgroup><tbody>')

    # --- 表头行样式 ---
    header_style = (
        'padding-top:1px;padding-right:1px;padding-left:1px;mso-ignore:padding;'
        'font-size:11.0pt;font-style:normal;text-decoration:none;'
        'mso-generic-font-family:auto;mso-number-format:General;'
        'vertical-align:middle;border:none;mso-background-source:auto;'
        'mso-pattern:auto;mso-protection:locked visible;mso-rotate:0;'
        'color:#B40000;font-weight:700;font-family:微软雅黑,sans-serif;'
        'mso-font-charset:134;text-align:center;'
        'border-top:none;border-right:none;border-bottom:1.5pt solid #B40000;border-left:none;'
        'white-space:normal;height:16.8pt;'
    )
    lines.append('<tr height="22" style="mso-height-source:auto;mso-ruby-visibility:none;height:16.8pt;">')
    for _, header, width, _ in columns:
        w_val = width.replace('pt', '')
        lines.append(
            f'<td align="center" dir="LTR" height="22" '
            f'style="{header_style}width:{width};" valign="middle" width="{w_val}">'
            f'{header}</td>'
        )
    lines.append('</tr>')

    # --- 数据行样式 ---
    cell_style = (
        'padding-top:1px;padding-right:1px;padding-left:1px;mso-ignore:padding;'
        'font-size:10.0pt;font-weight:400;font-style:normal;text-decoration:none;'
        'mso-generic-font-family:auto;mso-number-format:General;'
        'vertical-align:middle;border:none;mso-background-source:auto;'
        'mso-pattern:auto;mso-protection:locked visible;mso-rotate:0;'
        'color:black;font-family:微软雅黑,sans-serif;mso-font-charset:134;'
        'border-right:none;border-bottom:1.0pt solid #B40000;border-left:none;'
        'white-space:normal;border-top:none;'
    )
    for row in rows:
        lines.append('<tr height="45" style="mso-height-source:auto;mso-ruby-visibility:none;height:33.6pt;">')
        for key, _, width, align in columns:
            w_val = width.replace('pt', '')
            lines.append(
                f'<td align="{align}" dir="LTR" height="45" '
                f'style="{cell_style}text-align:{align};width:{width};" valign="middle" width="{w_val}">'
                f'{row.get(key, "")}</td>'
            )
        lines.append('</tr>')

    lines.append('</tbody></table>')
    return '\n'.join(lines)


# 本周计划表格列定义：序号 / 阶段 / 任务描述 / 时间 / 状态
_THIS_WEEK_COLS = [
    ('序号',     '序号',     '65pt', 'center'),
    ('阶段',     '阶段',     '65pt', 'center'),
    ('任务描述', '任务描述', '285pt', 'left'),
    ('时间',     '时间',     '65pt', 'center'),
    ('状态',     '状态',     '65pt', 'center'),
]

# 下周计划表格列定义：序号 / 阶段 / 任务描述 / 时间
_NEXT_WEEK_COLS = [
    ('序号',     '序号',     '58pt', 'center'),
    ('阶段',     '阶段',     '58pt', 'center'),
    ('任务描述', '任务描述', '340pt', 'left'),
    ('时间',     '时间',     '89pt', 'center'),
]


def _build_signature() -> str:
    """生成邮件签名 HTML"""
    return '''<div><sign signid="0"><div>
        <div style="color:#909090;font-family:Arial Narrow;font-size:12px"></div>
    </div>
    <div class="signRealArea" style="font-size:14px;font-family:Verdana;color:#000;">
        <div style="margin: 10px;">
            <p class="MsoNormal" style="font-family: &quot;Microsoft YaHei&quot;, 微软雅黑, -apple-system, BlinkMacSystemFont, &quot;PingFang SC&quot;, sans-serif; font-size: 14px; margin: 0px 0cm; caret-color: rgb(0, 0, 0); text-align: justify; line-height: normal;"><b style="font-family: verdana;"><font color="#999999" size="1">Sun Chong 孙冲</font></b></p>
            <div style="font-family: verdana;"><b style=""><font color="#999999" size="1" style=""><br>
                </font></b>
            </div>
            <div style="">
                <div style=""><font face="verdana" size="1"><i style=""><b style=""><font color="#ff0000">F</font><font color="#0080c0">ull-value </font><font color="#ff0000">L</font><font color="#0080c0">ogistics, </font><font color="#ff0000">U</font><font color="#0080c0">nited e</font><font color="#ff0000">X</font><font color="#0080c0">pertise</font></b></i></font></div>
                <div style=""><font face="verdana" size="1" style="    color: #1f497d;">专注.专业.专心</font></div>
                <div style="">
                    <span style="font-family: verdana;"><font size="1" style="    color: #1f497d;">---------------------------------------------</font></span>
                </div>
                <div style=""><font face="verdana" size="1" style="    color: #1f497d;">上海富勒信息科技有限公司（FLUX）</font></div>
                <div style=""><font size="1" style="    color: #1f497d;"><font face="verdana">客服: 400 878 9606&nbsp; 手机: 158 9885 2174 </font>
                    <span style="font-family: verdana;">&nbsp; </span>
                    </font>
                </div>
                <div style=""><font face="verdana" style="    color: #1f497d;"><font size="1">网址: http://www.flux.com.cn</font></font></div>
                <div style=""><img data-csp-key="data-csp-o6mdd9z909iatr9umsoh7ttnosmje4d2" src="https://exmail.qq.com/cgi-bin/viewfile?type=signature&amp;picid=ZX1923-HF80zCcKmDPrq2YDVjBLNee&amp;uin=3450596163" onerror=""></div>
            </div>
        </div>
    </div>
    </sign>
</div>'''


# ============================================================
# 主入口
# ============================================================

def process_pptx(pptx_path: str, output_dir: str = None, skip_pdf: bool = False):
    """
    处理单个 PPTX 文件：
      1. 导出 PDF
      2. 动态识别"本周/下周计划"页面 → 生成邮件 HTML
    返回: {'pdf': path, 'html': path}
    """
    pptx_path = os.path.abspath(pptx_path)
    if not os.path.exists(pptx_path):
        raise FileNotFoundError(f"文件不存在: {pptx_path}")

    if output_dir is None:
        output_dir = str(Path(pptx_path).parent.parent / 'outputs')
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    base_name = Path(pptx_path).stem
    result = {}

    # Step 1: PPTX → PDF
    if not skip_pdf:
        pdf_path = os.path.join(output_dir, f'{base_name}.pdf')
        result['pdf'] = pptx_to_pdf(pptx_path, pdf_path)
    else:
        print("[跳过] PDF 转换")

    # Step 2: 动态识别页面 & 提取数据 & 生成邮件 HTML
    print(f"[提取] 正在解析 PPTX 表格数据（按标题动态定位页面）...")
    data = extract_all_data(pptx_path)
    print(f"  - 项目: {data['project_name']}")
    print(f"  - 周数: {data['week_number']}")
    print(f"  - 本周计划: {len(data['this_week_rows'])} 条")
    print(f"  - 下周计划: {len(data['next_week_rows'])} 条")

    html_content = generate_email_html(data)
    html_path = os.path.join(output_dir, f'{base_name}-邮件内容.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[完成] 邮件 HTML 已保存至: {html_path}")
    result['html'] = html_path

    return result


def main():
    parser = argparse.ArgumentParser(
        description='项目周报处理工具 — 将 PPTX 导出为 PDF 并生成邮件 HTML\n'
                    '幻灯片页码按标题关键词动态识别，无需固定页码。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python generate_weekly_report.py 周报.pptx
  python generate_weekly_report.py 周报.pptx -o ./output
  python generate_weekly_report.py 周报.pptx --skip-pdf
  python generate_weekly_report.py 周报.pptx --pdf-only
        ''',
    )
    parser.add_argument(
        'input', nargs='?',
        default=None,
        help='PPTX 文件路径',
    )
    parser.add_argument(
        '-o', '--output-dir',
        default=None,
        help='输出目录（默认：PPTX 同级的 outputs 目录）',
    )
    parser.add_argument(
        '--skip-pdf',
        action='store_true',
        help='跳过 PDF 导出，仅生成邮件 HTML',
    )
    parser.add_argument(
        '--pdf-only',
        action='store_true',
        help='仅导出 PDF，不生成邮件 HTML',
    )

    args = parser.parse_args()

    if not args.input:
        print("错误: 请指定 PPTX 文件路径")
        print("用法: python generate_weekly_report.py <pptx_path>")
        sys.exit(1)

    input_path = os.path.abspath(args.input)

    # 统一输出目录：用户指定则用之，否则由 process_pptx 内部计算默认值
    output_dir = args.output_dir if args.output_dir else None

    print(f"输入文件: {input_path}")
    print(f"输出目录: {output_dir or '(默认: PPTX 同级 outputs 目录)'}")
    print()

    if args.pdf_only:
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(input_path), '..', 'outputs')
            output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        pdf_out = os.path.join(output_dir, Path(input_path).stem + '.pdf')
        pptx_to_pdf(input_path, pdf_out)
    else:
        process_pptx(input_path, output_dir, skip_pdf=args.skip_pdf)


if __name__ == '__main__':
    main()
