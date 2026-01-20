import streamlit as st
import json
import time
import _snowflake
from snowflake.snowpark.context import get_active_session

st.set_page_config(
    page_title="Bikes & Snow Agent",
    page_icon="🚴",
    layout="wide"
)

st.title("Bikes & Snow Agent Chat")
st.caption("Powered by Cortex Agent API")

DATABASE = "CC_SNOWFLAKE_INTELLIGENCE_E2E"
SCHEMA = "PUBLIC"
AGENT_NAME = "BIKES_SNOW_AGENT"
API_ENDPOINT = "/api/v2/databases/" + DATABASE + "/schemas/" + SCHEMA + "/agents/" + AGENT_NAME + ":run"
API_TIMEOUT = 120000

session = get_active_session()

if "messages" not in st.session_state:
    st.session_state.messages = []


def call_agent(user_message):
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_message}]
            }
        ]
    }
    
    resp = _snowflake.send_snow_api_request(
        "POST",
        API_ENDPOINT,
        {},
        {"stream": True},
        payload,
        None,
        API_TIMEOUT
    )
    
    if resp["status"] != 200:
        return None, "Error: HTTP " + str(resp["status"])
    
    return json.loads(resp["content"]), None


def parse_response(events):
    thinking = ""
    answer = ""
    sql = ""
    tools = []
    
    for event in events:
        event_type = event.get("event", "")
        data = event.get("data", {})
        
        if event_type == "response.thinking.delta":
            thinking = thinking + data.get("text", "")
        
        elif event_type == "response.text.delta":
            answer = answer + data.get("text", "")
        
        elif event_type == "response.tool_use.delta":
            tool_name = data.get("name", "")
            if tool_name and tool_name not in tools:
                tools.append(tool_name)
        
        elif event_type == "response":
            content_list = data.get("content", [])
            for item in content_list:
                if item.get("type") == "text":
                    answer = item.get("text", "")
                elif item.get("type") == "tool_use":
                    tool_name = item.get("name", "")
                    if tool_name and tool_name not in tools:
                        tools.append(tool_name)
                elif item.get("type") == "tool_results":
                    tool_content = item.get("tool_results", {}).get("content", [])
                    for tc in tool_content:
                        if tc.get("type") == "json":
                            json_data = tc.get("json", {})
                            if json_data.get("sql"):
                                sql = json_data["sql"]
    
    return thinking, answer, sql, tools


def stream_text(text, placeholder, delay=0.01):
    displayed = ""
    for char in text:
        displayed = displayed + char
        placeholder.markdown(displayed)
        time.sleep(delay)


def reset_conversation():
    st.session_state.messages = []


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message.get("thinking"):
            with st.expander("View Agent Thinking", expanded=False):
                st.code(message["thinking"])
        st.markdown(message["content"])
        if message.get("sql"):
            st.markdown("**Generated SQL:**")
            st.code(message["sql"], language="sql")


if prompt := st.chat_input("Ask a question about bikes or snow products..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Agent is processing your request..."):
            events, error = call_agent(prompt)
        
        if error:
            st.error(error)
            response_text = error
            thinking = ""
            sql = ""
        else:
            thinking, answer, sql, tools = parse_response(events)
            
            if thinking:
                with st.expander("View Agent Thinking", expanded=True):
                    thinking_placeholder = st.empty()
                    stream_text(thinking, thinking_placeholder, delay=0.005)
            
            if tools:
                st.caption("Tools used: " + ", ".join(tools))
            
            response_placeholder = st.empty()
            answer_clean = answer.replace("【†", "[").replace("†】", "]")
            stream_text(answer_clean, response_placeholder, delay=0.01)
            response_text = answer_clean
            
            if sql and sql.strip().upper().startswith("SELECT"):
                st.markdown("**Generated SQL:**")
                st.code(sql, language="sql")
                try:
                    results = session.sql(sql.replace(";", ""))
                    st.dataframe(results)
                except Exception as e:
                    st.error("Error executing SQL: " + str(e))
    
    valid_sql = ""
    if sql and sql.strip().upper().startswith("SELECT"):
        valid_sql = sql
    
    st.session_state.messages.append({
        "role": "assistant",
        "content": response_text,
        "sql": valid_sql,
        "thinking": thinking if thinking else ""
    })


with st.sidebar:
    st.header("Session Info")
    st.text("Messages: " + str(len(st.session_state.messages)))
    
    if st.button("New Conversation"):
        reset_conversation()
        st.rerun()
    
    st.divider()
    st.header("Agent Details")
    st.text("Database: " + DATABASE)
    st.text("Schema: " + SCHEMA)
    st.text("Agent: " + AGENT_NAME)
