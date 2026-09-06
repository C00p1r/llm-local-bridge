from handlers.core_handlers import register_core_handlers
from handlers.git_handlers import register_git_handlers
from handlers.search_handlers import register_search_handlers

def register_all_handlers():
    """集中註冊所有領域工具的處理常式"""
    register_core_handlers()
    register_git_handlers()
    register_search_handlers()
