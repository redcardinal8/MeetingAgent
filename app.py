import chainlit as cl
from agent import MeetingSchedulerAgent
import os

# Initialize the agent
agent = MeetingSchedulerAgent()

@cl.on_chat_start
async def start():
    # Display welcome message
    await cl.Message(
        content="Hello! I can help you schedule meetings on Cal.com or view your existing ones.\n\n"
                "I can help you with:\n"
                "1. Booking new meetings\n"
                "2. Viewing your scheduled meetings\n"
                "3. Cancelling meetings\n\n"
                "What would you like to do?"
    ).send()

@cl.on_message
async def main(message: cl.Message):
    # Get the user's message
    user_input = message.content

    # Process the message with the agent
    response = agent.chat(user_input)

    # Send the response back to the user
    await cl.Message(
        content=response
    ).send()

    # If the response contains a tool call result, format it nicely
    if "status" in response and "events" in response:
        try:
            import json
            response_data = json.loads(response)
            if response_data["status"] == "success":
                # Create a formatted message for the events
                events_message = f"📅 {response_data['message']}\n\n"
                for event in response_data["events"]:
                    events_message += f"📌 {event['title']}\n"
                    events_message += f"   ⏰ Start: {event['startTime']}\n"
                    events_message += f"   ⏰ End: {event['endTime']}\n"
                    if 'responses' in event:
                        events_message += f"   👥 Attendees: {event['responses'].get('name', 'N/A')} ({event['responses'].get('email', 'N/A')})\n"
                    events_message += "\n"
                
                await cl.Message(
                    content=events_message
                ).send()
        except Exception as e:
            print(f"Error formatting events: {e}")

# Chainlit configuration
@cl.on_settings_update
async def setup_agent(settings):
    # Update agent settings if needed
    pass 