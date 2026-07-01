from src.llm import get_llm
from src.memory import ChatMemory
from src.agent import MiniAgent
from src.registry import build_default_registry


def main():
    llm = get_llm()
    memory = ChatMemory()
    registry = build_default_registry()
    agent = MiniAgent(llm, registry)

    print("\n🤖  Mini Agent (ReAct)  |  type 'exit' to quit\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            print("AI: Goodbye, catch you soon!")
            break

        if not user_input:
            continue

        memory.add_user_message(user_input)
        result = agent.run(user_input, memory)

        # Show ReAct trace
        for step in result.get("trace", []):
            print(f"\n  [Step {step['step']}]", end="")
            if step.get("thought"):
                print(f"  THINK: {step['thought']}")
            if step.get("action"):
                print(f"  ACTION: {step['action']}")
            if step.get("observation"):
                obs_preview = step["observation"][:200]
                print(f"  OBSERVATION: {obs_preview}")
            if step.get("clarify"):
                print(f"  CLARIFY: {step['clarify']}")

        print(f"\nAI:\n{result['text']}\n")

        memory.add_ai_message(result["text"])


if __name__ == "__main__":
    main()
