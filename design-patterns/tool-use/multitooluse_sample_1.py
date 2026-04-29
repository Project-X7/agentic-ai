import requests
import litellm
import json

MODEL = "groq/openai/gpt-oss-120b" # llm which groq api calls

def get_weather_ip():
    """
    Gets the current, high, and low temperature in Fahrenheit for the user's
    location and returns it to the user.
    """
    lat, lon = requests.get('https://ipinfo.io/json').json()['loc'].split(',')
       # Set parameters for the weather API call
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "auto"
    }
    # Get weather data
    weather_data = requests.get("https://api.open-meteo.com/v1/forecast", params=params).json()
      # Format and return the simplified string
    return (
        f"Current: {weather_data['current']['temperature_2m']}°F, "
        f"High: {weather_data['daily']['temperature_2m_max'][0]}°F, "
        f"Low: {weather_data['daily']['temperature_2m_min'][0]}°F"
    )

# Write a text file
def write_txt_file(file_path: str, content: str):
    """
    Write a string into a .txt file (overwrites if exists).
    Args:
        file_path (str): Destination path.
        content (str): Text to write.
    Returns:
        str: Path to the written file.
    """
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


# info = get_weather_ip()
# print(info)

# file_path = write_txt_file("/Users/priyakhoesial/Dev/ai/agentic-ai/design-patterns/tool-useweather_info.txt", info)
# print(f"Weather information written to {file_path}")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather_ip",
            "description": (
                "Gets the current, high, and low temperature in Fahrenheit "
                "for the user's location based on their IP address. "
                "No arguments needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {},       # no args required
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_txt_file",
            "description": "Write text content into a .txt file at the given path. Overwrites if file already exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Destination file path, e.g. 'output/report.txt'"
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write into the file"
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    }
]


TOOLS = {
    "get_weather_ip": lambda args: get_weather_ip(),          # no args
    "write_txt_file": lambda args: write_txt_file(**args),
}

def execute_tool_call(tool_call) -> dict:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    if name not in TOOLS:
        result = {"error": f"Unknown tool: {name}"}
    else:
        try:
            result = TOOLS[name](args)
        except Exception as e:
            result = {"error": str(e)}

    return {
        "tool_call_id": tool_call.id,
        "name": name,
        "result": result
    }


def run_agent(user_message: str, model: str = "gpt-4o"):
    messages = [{"role": "user", "content": user_message}]
    print(f"\n USER: {user_message}\n")

    while True:
        response = litellm.completion(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            parallel_tool_calls=True
        )

        message = response.choices[0].message
        messages.append(message)

        # No tool calls → final answer
        if not message.tool_calls:
            print(f"\n ANSWER: {message.content}")
            return message.content

        print(f" Calling {len(message.tool_calls)} tool(s):")
        for tc in message.tool_calls:
            print(f"   → {tc.function.name}({tc.function.arguments})")

        # Execute and append results
        for tc in message.tool_calls:
            r = execute_tool_call(tc)
            print(f"   ✓ {r['name']} → {r['result']}")
            messages.append({
                "role": "tool",
                "tool_call_id": r["tool_call_id"],
                "content": json.dumps(r["result"])
            })

    if not os.environ.get("GROQ_API_KEY"):
        raise EnvironmentError(
            "GROQ_API_KEY not set.\n"
        )


run_agent("What's the current weather at my locatio")