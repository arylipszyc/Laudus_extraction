from pipeline.services.laudus_service import get_info_API

def fetch_balance_sheet(endpoint, params=None):
    """
    Fetches the balance sheet details from the Laudus API.
    
    Args:
        endpoint (str): The specific endpoint URL for the balance sheet.
        params (dict, optional): Query parameters like dates.
        
    Returns:
        dict: The JSON response containing the balance sheet data.
    """
    return get_info_API(endpoint, params)

