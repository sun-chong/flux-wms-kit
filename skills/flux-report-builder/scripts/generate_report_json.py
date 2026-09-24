#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报表 JSON 配置生成脚本
根据 SQL 查询语句和字段信息生成 FLUX WMS 报表配置
"""

import json

# 字段信息定义（根据数据库查询结果）
fields = [
    # 来自 ACT_TRANSACTION_LOG 表
    {"field": "organizationId", "label": "组织编号", "type": "VARCHAR2(20)", "width": "100", "align": "left", "sort": "str", "filterType": ""},
    {"field": "warehouseId", "label": "仓库编号", "type": "VARCHAR2(20)", "width": "100", "align": "left", "sort": "str", "filterType": ""},
    {"field": "transactionId", "label": "事务编号", "type": "VARCHAR2(20)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "docNo", "label": "单证编号", "type": "VARCHAR2(20)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "docLineNo", "label": "单据行号", "type": "INTEGER", "width": "80", "align": "right", "sort": "int", "filterType": ""},
    {"field": "toSku", "label": "目标产品", "type": "VARCHAR2(50)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "toId", "label": "目标跟踪号", "type": "VARCHAR2(30)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "toQty_Each", "label": "TO数量_EA", "type": "NUMBER(18,8)", "width": "100", "align": "right", "sort": "float", "filterType": ""},
    {"field": "operator", "label": "操作人", "type": "VARCHAR2(40)", "width": "100", "align": "left", "sort": "str", "filterType": ""},
    {"field": "transactionTime", "label": "事务时间", "type": "DATE", "width": "150", "align": "center", "sort": "date", "filterType": ""},
    {"field": "ediSendFlag", "label": "接口发送标记", "type": "CHAR(1)", "width": "100", "align": "center", "sort": "str", "filterType": ""},
    {"field": "ediSendTime", "label": "接口发送时间", "type": "DATE", "width": "150", "align": "center", "sort": "date", "filterType": ""},
    {"field": "ediErrorCode", "label": "EDI错误代码", "type": "VARCHAR2(50)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "ediErrorMessage", "label": "EDI错误信息", "type": "VARCHAR2(500)", "width": "200", "align": "left", "sort": "str", "filterType": ""},

    # 来自 DOC_ORDER_HEADER 表
    {"field": "customerId", "label": "货主", "type": "VARCHAR2(30)", "width": "100", "align": "left", "sort": "str", "filterType": ""},
    {"field": "orderType", "label": "订单类型", "type": "VARCHAR2(20)", "width": "100", "align": "left", "sort": "str", "filterType": ""},
    {"field": "udf01", "label": "自定义01", "type": "VARCHAR2(500)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "udf02", "label": "自定义02", "type": "VARCHAR2(500)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "waveNo", "label": "波次号", "type": "VARCHAR2(20)", "width": "100", "align": "left", "sort": "str", "filterType": ""},
    {"field": "soReference1", "label": "参考编号1", "type": "VARCHAR2(50)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "soReference2", "label": "参考编号2", "type": "VARCHAR2(50)", "width": "120", "align": "left", "sort": "str", "filterType": ""},

    # 来自 DOC_ORDER_DETAILS 表
    {"field": "lineStatus", "label": "行状态", "type": "VARCHAR2(2)", "width": "80", "align": "center", "sort": "str", "filterType": ""},
    {"field": "dedi05", "label": "EDI相关信息5", "type": "VARCHAR2(200)", "width": "150", "align": "left", "sort": "str", "filterType": ""},

    # 来自 INV_LOT_ATT 表
    {"field": "lotAtt04", "label": "批次属性04", "type": "VARCHAR2(100)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "lotAtt05", "label": "批次属性05", "type": "VARCHAR2(100)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "lotAtt06", "label": "批次属性06", "type": "VARCHAR2(100)", "width": "120", "align": "left", "sort": "str", "filterType": ""},

    # 来自 BSM_CODE_ML 表（通过 JOIN 获取）
    {"field": "sotyp", "label": "订单类型描述", "type": "VARCHAR2(100)", "width": "120", "align": "left", "sort": "str", "filterType": ""},
    {"field": "linests", "label": "行状态描述", "type": "VARCHAR2(100)", "width": "120", "align": "left", "sort": "str", "filterType": ""}
]

# 生成 items 数组
items = []
for i, field_info in enumerate(fields):
    item = {
        "id": 30001 + i,
        "field": field_info["field"],
        "udfLabel": field_info["label"],
        "width": field_info["width"],
        "cid": f"c{6001 + i}",
        "label": "",
        "sort": field_info["sort"],
        "align": field_info["align"],
        "type": "edtxt",
        "filterType": field_info["filterType"],
        "calTpl": "0000.00" if "NUMBER" in field_info["type"] else "",
        "isCal": "N",
        "udfFormat": "",
        "conFormName": "",
        "conFormField": "",
        "pkFlag": "N",
        "copyFlag": "Y",
        "mustInput": "N",
        "defaultValue": "",
        "transName": "",
        "defTransNameFlag": "N",
        "showVirtual": "N",
        "virtualType": "",
        "virtualFormula": "",
        "batchCopyFlag": "N",
        "dispCondExpr": "Y",
        "dispCondExprType": "",
        "fixedWidth": "N"
    }
    items.append(item)

# 构建 gridPro
grid_pro = [{
    "id": 20000 + len(items) + 1,
    "widgetName": "detailsGrid",
    "freezeField": "",
    "subFunctions": [],
    "items": items,
    "mainTableName": "ACT_TRANSACTION_LOG",
    "mainTableDescField": "transactionId",
    "mainTablePKField": "transactionId",
    "addCheckField": "",
    "addShowField": "",
    "addRefreshField": "",
    "addRefreshFieldAfterDelete": "",
    "calLogicType": "1",
    "calLogicField": "",
    "calLogicField2": "",
    "filterType": "1",
    "enablePage": "Y",
    "pageSize": "100",
    "enableSummary": "N",
    "enableExport": "Y",
    "enableImport": "N",
    "enableBatchCopy": "N",
    "enableBatchDelete": "N",
    "enableRowCopy": "N",
    "enableAdd": "N",
    "enableDelete": "N",
    "enableEdit": "N",
    "enableSort": "Y",
    "enableFilter": "Y",
    "enableGroup": "N",
    "enablePivot": "N",
    "enableChart": "N",
    "enableConditionalFormatting": "N",
    "enableDataValidation": "N",
    "enableAutoComplete": "N",
    "enableAutoSave": "N",
    "enableAutoRefresh": "N",
    "enableAutoCalc": "N",
    "enableAutoFilter": "Y",
    "enableAutoSort": "Y",
    "enableAutoGroup": "N",
    "enableAutoPivot": "N",
    "enableAutoChart": "N",
    "enableAutoConditionalFormatting": "N",
    "enableAutoDataValidation": "N",
    "enableAutoCompleteOnFocus": "N",
    "enableAutoSaveOnBlur": "N",
    "enableAutoRefreshOnLoad": "N",
    "enableAutoCalcOnLoad": "N"
}]

# 输出 JSON
print(json.dumps(grid_pro, ensure_ascii=False, indent=2))

# 保存到文件
with open('C:\\Users\\25632\\AI_Space\\Projects_Dev\\DongCheng\\outputs\\C0104_AZTTMESSO_detailsGrid.json', 'w', encoding='utf-8') as f:
    json.dump(grid_pro, f, ensure_ascii=False, indent=2)

print("\nJSON 配置已保存到: outputs/C0104_AZTTMESSO_detailsGrid.json")
