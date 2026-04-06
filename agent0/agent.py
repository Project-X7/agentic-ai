from google.adk.agents.llm_agent import Agent

# Mock toll implementation
def get_current_time(city: str) -> dict:
    """ returns current time in a given city """
    return {"status": "success", "time": "10:00 AM", "city": city}

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='A helpful assistant for user questions.',
    instruction='Answer user questions to the best of your knowledge',
    tools=[get_current_time],
)
