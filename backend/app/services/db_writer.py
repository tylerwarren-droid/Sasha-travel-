import logging, os
from typing import Optional
import httpx
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger("kanoe.db_writer")
SUPABASE_URL = os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY","")
_HEADERS = {"apikey":SUPABASE_SERVICE_KEY,"Authorization":f"Bearer {SUPABASE_SERVICE_KEY}","Content-Type":"application/json","Prefer":"return=representation"}
def _configured(): return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
def _strip_none(d): return {k:v for k,v in d.items() if v is not None}
async def write_trip_item(trip_id,type,status="attempting",booking_reference=None,provider_name=None,provider_email=None,provider_phone=None,date_time=None,duration_minutes=None,location_name=None,location_address=None,location_lat=None,location_lng=None,price_usd=None,currency=None,confirmation_deadline=None,escalation_notes=None):
    if not trip_id: return None
    if not _configured(): logger.warning("[db_writer] not configured"); return None
    payload = _strip_none({"trip_id":trip_id,"type":type,"status":status,"booking_reference":booking_reference,"provider_name":provider_name,"provider_email":provider_email,"provider_phone":provider_phone,"date_time":date_time,"duration_minutes":duration_minutes,"location_name":location_name,"location_address":location_address,"location_lat":location_lat,"location_lng":location_lng,"price_usd":price_usd,"currency":currency,"confirmation_deadline":confirmation_deadline,"escalation_notes":escalation_notes})
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(f"{SUPABASE_URL}/rest/v1/trip_items",headers=_HEADERS,json=payload)
            r.raise_for_status(); rows=r.json(); item_id=rows[0]["id"] if rows else None
            logger.info(f"[db_writer] trip_item created: {item_id}"); return item_id
    except Exception as e: logger.error(f"[db_writer] write_trip_item failed: {e}"); return None
async def update_trip_item(item_id,status=None,booking_reference=None,provider_name=None,provider_email=None,provider_phone=None,date_time=None,location_name=None,location_address=None,price_usd=None,escalation_notes=None):
    if not item_id: return False
    if not _configured(): return False
    payload = _strip_none({"status":status,"booking_reference":booking_reference,"provider_name":provider_name,"provider_email":provider_email,"provider_phone":provider_phone,"date_time":date_time,"location_name":location_name,"location_address":location_address,"price_usd":price_usd,"escalation_notes":escalation_notes})
    if not payload: return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.patch(f"{SUPABASE_URL}/rest/v1/trip_items?id=eq.{item_id}",headers=_HEADERS,json=payload)
            r.raise_for_status(); logger.info(f"[db_writer] updated: {item_id}"); return True
    except Exception as e: logger.error(f"[db_writer] update failed: {e}"); return False
async def write_booking_attempt(trip_item_id,method,status="sent",response_received=None,bland_call_id=None,resend_email_id=None,browserbase_session_id=None):
    if not trip_item_id: return None
    if not _configured(): return None
    payload = _strip_none({"trip_item_id":trip_item_id,"method":method,"status":status,"response_received":response_received,"bland_call_id":bland_call_id,"resend_email_id":resend_email_id,"browserbase_session_id":browserbase_session_id})
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(f"{SUPABASE_URL}/rest/v1/booking_attempts",headers=_HEADERS,json=payload)
            r.raise_for_status(); rows=r.json(); return rows[0]["id"] if rows else None
    except Exception as e: logger.error(f"[db_writer] write_booking_attempt failed: {e}"); return None