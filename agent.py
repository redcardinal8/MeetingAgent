import os
import json
import requests 
from openai import OpenAI
from datetime import datetime, timedelta, timezone as dt_timezone # Added timezone
from zoneinfo import ZoneInfo # For handling timezones



# Cal.com Configuration
CAL_COM_API_KEY = os.environ.get("CAL_COM_API_KEY") # IMPORTANT: Set this environment variable
CAL_COM_BASE_URL = "https://api.cal.com/v1"
CAL_COM_FIND_URL = "https://api.cal.com/v2"

if not CAL_COM_API_KEY:
    print("WARNING: CAL_COM_API_KEY environment variable not set. Cal.com features may not work as expected.")

try:
    client = OpenAI()
except Exception as e: # More general exception
    print(f"OpenAI API key not found or invalid, or other initialization error. Please set the OPENAI_API_KEY environment variable.")
    print(f"Error: {e}")
    exit()

class MeetingSchedulerAgent:
    def __init__(self):
        self.client = client
        self.cal_api_key = CAL_COM_API_KEY
        self.cal_base_url = CAL_COM_BASE_URL
        self.cal_find_url = CAL_COM_FIND_URL
        
        self.system_prompt = {
            "role": "system",
            "content": """You are a chatbot that assists users in booking meetings on Cal.com and retrieving their scheduled Cal.com events.

You should engage users to gather necessary details:
- For booking: Meeting reason/title, participants (emails, names), desired date, time, their timezone (e.g., 'America/New_York'), the Cal.com Event Type ID, and meeting duration in minutes. The chatbot will check Cal.com for availability.
- For retrieving events: User's email associated with Cal.com.
- For cancelling meetings: User's email, meeting date and time, and reason for cancellation (optional).

# Steps

1. **Booking a Meeting (on Cal.com):**
   - Ask the user for: meeting's title, responses (participant's name, email, location), date, start time, timezone of participants), Cal.com Event Type ID, duration (in minutes), the language of the meeting, and event description. 
   - Make sure the timezone of the user is also specified.
   - (Optional but recommended: Check Cal.com for availability of the requested time slot for the given Event Type ID and duration using /slots API).
   - If available (or proceeding directly), create a new event in the user's Cal.com schedule using /bookings API.
   - Confirm the booking with the user and provide the event details.

2. **Retrieving Scheduled Events (from Cal.com):**
   - Ask the user for the attendee's email.
   - Take the json of the response from the /bookings API to retrieve all scheduled events for that user and present the important fields in a nicer fashion.
   - Create a list of these bookings.

3. **Cancelling a Meeting:**
   - Ask the user for their email, the reason why they want to cancel the meeting (if user doesn't give reason leave a blank string), and the time and date of the meeting they want to cancel. 
   - Retrieve the booking UID using the /bookings API.
   - Use the /bookings/{id} API to cancel the meeting.

# Output Format

For booking a meeting:
- Confirm with: "Your meeting '[title]' has been scheduled on Cal.com for [date] at [time] [timezone] for [duration] minutes. Event Type ID: [eventTypeId]. Cal.com Booking ID: [cal_com_booking_id]."

For retrieving events:
- Provide a list: 
  - "Scheduled Cal.com Events for [email] on [date] ([timezone]):"
  - "[Event Title 1]: Start: [startTime] (UTC), End: [endTime] (UTC), Attendees: [names/emails]"
  - ... (Note: Cal.com returns times in UTC, inform the user or convert if possible)

For cancelling a meeting:
- Confirm with: "Your meeting '[title]' scheduled for [date] at [time] has been successfully cancelled."
- If the meeting cannot be found or cancelled, inform the user with the specific reason.

# Notes
- Always ask for and use timezones for accurate scheduling.
- If Cal.com API key is missing or invalid, inform the user you cannot perform Cal.com operations.
- Handle API errors from Cal.com gracefully.
- An Event Type ID is crucial for booking on Cal.com. If the user doesn't know it, guide them to find it in their Cal.com account.
- For participants, collect their email, name, and timezone.
"""
        }
        self.messages = [self.system_prompt]

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "book_cal_com_meeting",
                    "description": "Books a meeting on Cal.com. It's recommended to have checked slot availability first if possible.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "eventTypeId": {"type": "integer", "description": "The numeric ID of the Cal.com event type to book."},
                            "meeting_title": {"type": "string", "description": "Title or subject of the meeting."},                          
                            "date": {"type": "string", "description": "Date of the meeting in YYYY-MM-DD format."},
                            "start": {"type": "string", "description": "Start time of the meeting in HH:MM format (24-hour)."},
                            "responses": {
                                "type": "object",
                                "description": "Responses for the meeting, including participant details.",
                                "properties": {
                                    "name": {"type": "string", "description": "Name of the participant."},
                                    "email": {"type": "string", "description": "Email address of the participant."},
                                    "location": {"type": "object", 
                                                 "description": "Location of the participant, if applicable.",
                                                 "properties": {
                                                    "optionValue": {"type": "string", "description": "Other information about the location, if any."},
                                                    "value": {"type": "string", "description": "Type of location, e.g., 'online', 'in-person'."},
                                                 },
                                                 "required": ["optionValue","value"],
                                                 "additionalProperties": False}
                                },
                                "required": ["name", "email", "location"],
                                "additionalProperties": False
                            },
                            "timeZone": {"type": "string", "description": "The timezone for the specified date and time, e.g., 'Europe/Berlin'."},
                            "duration_minutes": {"type": "integer", "description": "Duration of the meeting in minutes."},
                            "language": {"type": "string", "description": "Language of the meeting, e.g., 'English', 'Spanish', etc."},
                            "metadata": { "type" : "object",
                                          "description": "Additional metadata for the meeting, such as description or notes.",
                                          "properties": {
                                              "description": {"type": "string", "description": "Description or notes for the meeting."}
                                          },
                                          "required": ["description"],
                                          "additionalProperties": False
                                        }
                        },
                        "required": ["eventTypeId", "responses", "meeting_title", "date", "start", "timeZone", "duration_minutes", "language", "metadata"],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "show_cal_com_booked_meetings",
                    "description": "Shows booked meetings from Cal.com for a given user email.",
                    "strict" : True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attendeeEmail": {"type": "string", "description": "Email of the attendee to retrieve meetings for."},
                        },
                        "required": ["attendeeEmail"],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_cal_com_meeting",
                    "description": "Cancels a meeting on Cal.com for a specific date and time.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attendeeEmail": {"type": "string", "description": "Email of the attendee whose meeting is to be cancelled."},
                            "date": {"type": "string", "description": "Date of the meeting to cancel in YYYY-MM-DD format."},
                            "start": {"type": "string", "description": "Start time of the meeting to cancel in HH:MM format (24-hour)."},
                            "timeZone": {"type": "string", "description": "The timezone for the specified date and time, e.g., 'Europe/Berlin'."},
                            "reason": {"type": "string", "description": "Reason for cancelling the meeting (optional)."}
                        },
                        "required": ["attendeeEmail", "date", "start", "timeZone", "reason"],
                        "additionalProperties": False
                    }
                }
            }
        ]

    def _make_cal_request(self, method, endpoint, params=None, json_data=None):
        if not self.cal_api_key:
            return {"error": "Cal.com API key not configured. Cannot perform Cal.com operations."}
        
        url = f"{self.cal_base_url}{endpoint}"
        
        headers = {"Content-Type": "application/json"} 
        
        query_params = {"apiKey": self.cal_api_key}
        if params:
            query_params.update(params)

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=query_params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, params={"apiKey": self.cal_api_key}, json=json_data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params={"apiKey": self.cal_api_key}, json=json_data)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}
            
            response.raise_for_status() 
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_message = f"HTTP error: {e.response.status_code}"
            try:
                error_details = e.response.json()
                error_message += f" - {error_details}"
            except json.JSONDecodeError:
                error_message += f" - {e.response.text}"
            print(f"[Cal.com API Error] {error_message}")
            return {"error": error_message, "status_code": e.response.status_code, "raw_text": e.response.text}
        except requests.exceptions.RequestException as e:
            error_details = f"Request exception: {e}"
            print(f"[Cal.com API Error] {error_details}")
            return {"error": error_details}
        except json.JSONDecodeError:
            error_details = "Failed to decode JSON response from Cal.com API."
            print(f"[Cal.com API Error] {error_details}")
            return {"error": error_details}
    
    def _make_cal_request_find(self, method, endpoint, params=None, json_data=None):
        if not self.cal_api_key:
            return {"error": "Cal.com API key not configured. Cannot perform Cal.com operations."}
        
        if not self.cal_api_key.startswith('cal_live_'):
            print(f"[WARNING] API key format may be incorrect. Expected format: cal_live_*")
        
        url = f"{self.cal_find_url}{endpoint}"
        
        # Set headers to match the working cURL request
        headers = {
            "Authorization": f"Bearer {self.cal_api_key}",
            "Content-Type": "application/json"
        }
        
        query_params = {}
        if params:
            query_params.update(params)

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=query_params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=json_data)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}
            
            response.raise_for_status() 
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_message = f"HTTP error: {e.response.status_code}"
            try:
                error_details = e.response.json()
                error_message += f" - {error_details}"
            except json.JSONDecodeError:
                error_message += f" - {e.response.text}"
            return {"error": error_message, "status_code": e.response.status_code, "raw_text": e.response.text}
        except requests.exceptions.RequestException as e:
            error_details = f"Request exception: {e}"
            return {"error": error_details}
        except json.JSONDecodeError:
            error_details = "Failed to decode JSON response from Cal.com API."
            return {"error": error_details}

    def _book_cal_com_meeting_impl(self, eventTypeId, responses, meeting_title, date, start, timeZone, duration_minutes, language, metadata):
        print(f"[Debug Function Call] book_cal_com_meeting: eventTypeId={eventTypeId}, title={meeting_title}, date={date}, time={start}, tz={timeZone}, duration={duration_minutes}")

        if not self.cal_api_key:
             return json.dumps({"status": "failure", "message": "Cal.com API key not configured in the agent."})

        try:
            user_tz = ZoneInfo(timeZone)
            localized_start = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M").replace(tzinfo=user_tz)
            localized_end = localized_start + timedelta(minutes=duration_minutes)

            start_iso_for_booking = localized_start.isoformat()
            end_iso_for_booking = localized_end.isoformat()

        except ValueError:
            return json.dumps({"status": "failure", "message": "Invalid date or time format. Please use YYYY-MM-DD and HH:MM."})

        booking_payload = {
            "eventTypeId": eventTypeId,
            "start": start_iso_for_booking,
            "end": end_iso_for_booking,
            "responses": responses, 
            "timeZone": timeZone,
            "language": language,
            "title": meeting_title,
            "metadata": metadata,
            "status": "ACCEPTED" 
        }

        booking_response = self._make_cal_request("POST", "/bookings", json_data=booking_payload)

        if booking_response and "error" not in booking_response and booking_response.get('id'): # Successful booking usually has an 'id'
            return json.dumps({
                "status": "success",
                "message": "Meeting successfully booked on Cal.com.",
                "meeting_details": {
                    "cal_com_booking_id": booking_response.get("id"),
                    "title": booking_response.get("title"),
                    "startTime_utc": booking_response.get("startTime"), # Cal.com returns this in UTC
                    "endTime_utc": booking_response.get("endTime"),     # Cal.com returns this in UTC
                    "eventTypeId": eventTypeId,
                    "requested_timeZone": timeZone,
                    "duration_minutes": duration_minutes,
                    "responses": responses,
                    "language": language,
                    "metadata": metadata
                }
            })
        else:
            error_msg = "Unknown error during booking."
            if booking_response and isinstance(booking_response, dict):
                error_msg = booking_response.get('message', booking_response.get('error', error_msg))
                if 'raw_text' in booking_response: # Add more context if available
                    error_msg += f" (Details: {booking_response['raw_text'][:200]})" # Truncate for brevity
            
            status_code = booking_response.get('status_code', None) if isinstance(booking_response, dict) else None
            if status_code == 409: 
                 error_msg = "The requested time slot is unavailable or conflicts with booking rules on Cal.com."
            return json.dumps({"status": "failure", "message": f"Failed to book meeting on Cal.com: {error_msg}"})


    def _show_cal_com_booked_meetings_impl(self, attendeeEmail): 
        
        if not self.cal_api_key:
             return json.dumps({"status": "failure", "message": "Cal.com API key not configured in the agent."})

        params = {
            "attendeeEmail": attendeeEmail
        }
            
        # Make sure we're using the correct endpoint
        bookings_data = self._make_cal_request_find("GET", "/bookings", params=params)

        if bookings_data and "error" not in bookings_data:
            # The response has a nested structure: status -> data -> bookings
            if isinstance(bookings_data, dict) and bookings_data.get('status') == 'success':
                data = bookings_data.get('data', {})
                if isinstance(data, dict) and 'bookings' in data:
                    bookings_list = data['bookings']
                    if not bookings_list: # Empty list means no bookings
                        return json.dumps({
                            "status": "success",
                            "message": f"No meetings found for {attendeeEmail}.",
                            "events": []
                        })
                    
                    return json.dumps({
                        "status": "success",
                        "message": f"Scheduled Cal.com Events for {attendeeEmail}:",
                        "events": bookings_list
                    })
            else:
                error_msg = "Unexpected response format from Cal.com API"
                return json.dumps({"status": "failure", "message": f"Failed to retrieve meetings from Cal.com: {error_msg}"})
        else:
            error_msg = "Unknown error retrieving meetings."
            if bookings_data and isinstance(bookings_data, dict): # Error responses are often dicts
                 error_msg = bookings_data.get('error', error_msg)
                 if 'raw_text' in bookings_data:
                     error_msg += f" (Details: {bookings_data['raw_text'][:200]})"
                 if 'status_code' in bookings_data:
                     error_msg += f" (Status Code: {bookings_data['status_code']})"
            return json.dumps({"status": "failure", "message": f"Failed to retrieve meetings from Cal.com: {error_msg}"})

    def _cancel_cal_com_meeting_impl(self, attendeeEmail, date, start, timeZone, reason=""):
        if not self.cal_api_key:
            return json.dumps({"status": "failure", "message": "Cal.com API key not configured in the agent."})

        try:
            # First, get all bookings for the user
            params = {
                "attendeeEmail": attendeeEmail
            }
            bookings_data = self._make_cal_request_find("GET", "/bookings", params=params)

            if not bookings_data or "error" in bookings_data:
                return json.dumps({"status": "failure", "message": "Failed to retrieve bookings to find the meeting to cancel."})

            # Find the booking that matches the date and time
            target_booking = None
            user_tz = ZoneInfo(timeZone)
            target_time = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M").replace(tzinfo=user_tz)
            
            if isinstance(bookings_data, dict) and bookings_data.get('status') == 'success':
                data = bookings_data.get('data', {})
                if isinstance(data, dict) and 'bookings' in data:
                    for booking in data['bookings']:
                        booking_time = datetime.fromisoformat(booking['startTime'].replace('Z', '+00:00'))
                        if booking_time.astimezone(user_tz) == target_time:
                            target_booking = booking
                            break

            if not target_booking:
                return json.dumps({"status": "failure", "message": f"No meeting found for {attendeeEmail} on {date} at {start} {timeZone}."})

            # Cancel the booking using DELETE method
            booking_id = target_booking['id']
            cancel_payload = {
                "reason": reason
            }
            
            # Use DELETE method instead of POST
            cancel_response = self._make_cal_request("DELETE", f"/bookings/{booking_id}", json_data=cancel_payload)

            if cancel_response and "error" not in cancel_response:
                return json.dumps({
                    "status": "success",
                    "message": f"Successfully cancelled meeting '{target_booking['title']}' scheduled for {date} at {start} {timeZone}.",
                    "booking_details": target_booking
                })
            else:
                error_msg = "Unknown error during cancellation."
                if cancel_response and isinstance(cancel_response, dict):
                    error_msg = cancel_response.get('message', cancel_response.get('error', error_msg))
                return json.dumps({"status": "failure", "message": f"Failed to cancel meeting: {error_msg}"})

        except Exception as e:
            return json.dumps({"status": "failure", "message": f"Error processing cancellation request: {str(e)}"})

    def chat(self, user_input):
        self.messages.append({"role": "user", "content": user_input})
        
        MAX_TURNS = 7 
        turn_count = 0

        while turn_count < MAX_TURNS:
            turn_count += 1
            if not self.cal_api_key and any(intent in user_input.lower() for intent in ["book", "show", "meeting", "schedule", "cal.com", "cancel"]):
                no_key_message = "I can't perform Cal.com operations because the Cal.com API key is not configured. Please ask the administrator to set it up."
                self.messages.append({"role": "assistant", "content": no_key_message})
                return no_key_message

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o", 
                    messages=self.messages,
                    tools=self.tools,
                    tool_choice="auto" 
                )
            except Exception as e:
                print(f"Error calling OpenAI API: {e}")
                self.messages.append({"role": "assistant", "content": "Sorry, I encountered an error communicating with the AI service."})
                return "Sorry, I encountered an error trying to connect to the AI service."

            response_message = response.choices[0].message
            self.messages.append(response_message)

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    if function_name == "book_cal_com_meeting":
                        function_response_content = self._book_cal_com_meeting_impl(**function_args)
                    elif function_name == "show_cal_com_booked_meetings":
                        function_response_content = self._show_cal_com_booked_meetings_impl(**function_args)
                    elif function_name == "cancel_cal_com_meeting":
                        function_response_content = self._cancel_cal_com_meeting_impl(**function_args)
                    else:
                        print(f"[Error] Unknown function called: {function_name}")
                        function_response_content = json.dumps({"status": "error", "message": f"Unknown function: {function_name}"})
                    
                    self.messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response_content,
                    })
            else:
                assistant_reply = response_message.content
                return assistant_reply
        
        return "Sorry, I couldn't complete your request after a few attempts. There might be an issue with repeated function calls or understanding the final step."

# Main interaction
if __name__ == "__main__":

    agent = MeetingSchedulerAgent()
    print("\nAI Agent: Hello! I can help you schedule meetings on Cal.com or view your existing ones.")
    print("AI Agent: For Cal.com actions, ensure your Cal.com API key is configured.")
    print("AI Agent: To book, I'll generally need: Event Type ID, date, time, timezone, duration, title, participant details, and the description of the meeting.")
    print("AI Agent: To view meetings, I'll need your Cal.com email, the date, and your timezone context.")
    print("AI Agent: To cancel a meeting, please provide the date, time, timezone, and reason (optional).")
    print("--------------------------------------------------------------------")


    while True:
        user_text = input("You: ")
        if user_text.lower() in ["exit", "quit", "bye", "goodbye"]:
            print("AI Agent: Goodbye! Have a great day.")
            break
        
        if not user_text.strip():
            continue

        assistant_response = agent.chat(user_text)
        print(f"AI Agent: {assistant_response}")