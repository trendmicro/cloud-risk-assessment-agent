import os
import asyncio

from conductor.client.automator.task_handler import TaskHandler # type: ignore
from conductor.client.configuration.configuration import Configuration # type: ignore
from conductor.client.configuration.settings.authentication_settings import AuthenticationSettings # type: ignore
from conductor.client.worker.worker_task import worker_task #type: ignore

from src.db.db_setup import setup_database_connections
from src.db.db_query import query_summary

class ConductorManager:
    api_config = None
    task_handler = None
    
    def __init__(self):
        self.api_config = Configuration(
            server_api_url=os.getenv("CONDUCTOR_URL",""),
            authentication_settings=AuthenticationSettings(
                key_id=os.getenv("CONDUCTOR_AUTH_KEY",""),
                key_secret=os.getenv("CONDUCTOR_AUTH_SECRET","")
            )
        )

        print("Starting workers")

        self.task_handler = TaskHandler(
            workers=[],
            configuration=self.api_config,
            scan_for_annotated_workers=True,
            import_modules=[]
        )

        self.task_handler.start_processes()
        

    def __del__(self):
        self.task_handler.stop_processes()


@worker_task(task_definition_name='Parse_Command')
def parse_command(query: str) -> str:
    category = "GENERIC"

    command_prefix = "/report "

    VALID_REPORT_CATEGORIES = {"code", "container", "aws", "kubernetes", "all"}
    
    if query.startswith(command_prefix):
        argument = query[len(command_prefix):].strip()    
        if argument and argument in VALID_REPORT_CATEGORIES:
            category = argument
    
    return category

@worker_task(task_definition_name='Query_Summary')
def query_summary_from_db(category:str):
    app_context = setup_database_connections()

    # Query database for summary data
    summary_df, table_df = asyncio.run(query_summary(app_context.get_connection(), category))
    
    result = table_df.to_string(index=False)
    top5 = table_df.to_string()
    summary = summary_df.to_string(index=False)
    
    return {"result":result, "summary": summary, "top5": top5}

@worker_task(task_definition_name='Generate_Insight')
def generate_insight(top5:str):
    return top5

@worker_task(task_definition_name='Generate_Conclusion')
def generate_conclusion(result:str):
    return result