import json
import oracledb

# 读取数据库连接配置（项目根目录 .env，需在项目根目录执行）
with open(r".env", 'r', encoding='utf-8') as f:
    env_values = {}
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        env_values[key.strip()] = value.strip()

db_connection = env_values['DB_CONNECTION']

# 解析连接字符串
parts = db_connection.split('@')
user_pass = parts[0].split('/')
username = user_pass[0]
password = user_pass[1]
host_port_service = parts[1].split(':')
host = host_port_service[0]
port_service = host_port_service[1].split('/')
port = int(port_service[0])
service_name = port_service[1]

# 连接数据库（thin mode，不需要 Oracle Client）
connection = oracledb.connect(
    user=username,
    password=password,
    dsn=oracledb.makedsn(host, port, service_name=service_name)
)

# 读取 JSON 文件
json_file_path = r"outputs\C0104_AZTTMESSO_20260604.json"
with open(json_file_path, 'r', encoding='utf-8') as f:
    json_data = json.load(f)

json_str = json.dumps(json_data, ensure_ascii=False, indent=2)

# 执行 INSERT
cursor = connection.cursor()
insert_sql = """
INSERT INTO DEV_UDFFUNCFG_WIDGET
(ORGANIZATIONID, FUNCTIONID, WIDGETNAME, JSONDATA, ACTIVEFLAG,
 CURRENTVERSION, OPRSEQFLAG, ADDWHO, EDITWHO, ADDTIME, EDITTIME)
VALUES
(:org_id, :func_id, :widget_name, :json_data, :active_flag,
 :current_version, :opr_seq_flag, :add_who, :edit_who, SYSDATE, SYSDATE)
"""

cursor.execute(insert_sql, {
    'org_id': 'ND',
    'func_id': 'C0104_AZTTMESSO',
    'widget_name': 'headerGrid',
    'json_data': json_str,
    'active_flag': 'Y',
    'current_version': 100,
    'opr_seq_flag': '2022',
    'add_who': 'ZHOUTT',
    'edit_who': 'ZHOUTT'
})
connection.commit()

print("INSERT 执行成功！")

# 验证结果
cursor.execute("""
SELECT FUNCTIONID, WIDGETNAME, LENGTH(JSONDATA) AS JSON_LENGTH, CURRENTVERSION
FROM DEV_UDFFUNCFG_WIDGET
WHERE ORGANIZATIONID = 'ND' AND FUNCTIONID = 'C0104_AZTTMESSO'
""")
result = cursor.fetchone()
if result:
    print(f"功能编号: {result[0]}")
    print(f"组件名称: {result[1]}")
    print(f"JSON 长度: {result[2]} 字节")
    print(f"版本号: {result[3]}")

# 验证 JSON 内容
cursor.execute("""
SELECT JSONDATA
FROM DEV_UDFFUNCFG_WIDGET
WHERE ORGANIZATIONID = 'ND' AND FUNCTIONID = 'C0104_AZTTMESSO'
""")
result = cursor.fetchone()
if result:
    json_content = result[0].read()  # CLOB 类型需要 .read()
    json_data = json.loads(json_content)

    # 检查 items 数量
    print(f"items 数量: {len(json_data['items'])}")

    # 检查第一个字段的 udfLabel
    print(f"第一个字段的 udfLabel: {json_data['items'][0]['udfLabel']}")

    # 检查小驼峰字段
    fields = [item['field'] for item in json_data['items']]
    print(f"包含 addWho: {'addWho' in fields}")
    print(f"包含 addTime: {'addTime' in fields}")
    print(f"包含 editWho: {'editWho' in fields}")
    print(f"包含 editTime: {'editTime' in fields}")

    # 检查 widgetName
    print(f"widgetName: {json_data['gridPro'][0]['widgetName']}")

cursor.close()
connection.close()
