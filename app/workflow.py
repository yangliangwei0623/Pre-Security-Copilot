from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from app.rules import questions_for, build_report


class State(TypedDict, total=False):
    items: list[dict]
    trip: dict
    bundle: dict
    questions: list[dict]
    report: dict


def build_graph(checkpointer):
    def assess(state):
        return {"questions": questions_for(state["bundle"], state["items"], state["trip"])}

    def ask(state):
        answers = interrupt({"questions": state["questions"]})
        items = [{**i, "attributes": dict(i["attributes"]), "provenance": dict(i["provenance"])} for i in state["items"]]
        for q in state["questions"]:
            item = next(i for i in items if i["id"] == q["item_id"])
            item["attributes"][q["field"]] = answers[q["id"]]
            item["provenance"][q["field"]] = "user" if answers[q["id"]] is not None else "unknown"
        return {"items": items}

    def report(state):
        return {"report": build_report(state["bundle"], state["items"], state["trip"])}

    graph = StateGraph(State)
    graph.add_node("assess", assess)
    graph.add_node("ask", ask)
    graph.add_node("report", report)
    graph.add_edge(START, "assess")
    graph.add_conditional_edges("assess", lambda s: "ask" if s["questions"] else "report")
    graph.add_edge("ask", "assess")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)
