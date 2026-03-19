import os
from dotenv import load_dotenv
from databricks import sql
import pandas as pd

load_dotenv()

def load_data():
    connection = sql.connect(
        server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN")
    )

    cursor = connection.cursor()
    
    query = "SELECT * FROM workspace.default.facilities_dataset LIMIT 1"

    cursor.execute(query)
    results = cursor.fetchall()
    print(results)

    cursor.close()
    connection.close()

    # return pd.read_sql(query, conn)

load_data()