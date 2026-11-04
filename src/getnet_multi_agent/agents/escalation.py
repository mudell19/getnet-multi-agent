"""Human Escalation agent. It uses no LLM, so it still works when the LLM or the budget does not."""
from getnet_multi_agent.tools.tickets import TicketStore

MESSAGES = {
    "en": "I've forwarded your request to our support team. Your ticket number is {ticket_id}, and a person will follow up with you.",
    "pt": "Encaminhei seu pedido para nossa equipe de atendimento. O número do seu chamado é {ticket_id}, e uma pessoa dará continuidade ao atendimento.",
}
FAILED = {
    "en": "I couldn't complete your request, and I also couldn't record a support ticket. Please contact Getnet's support channels directly.",
    "pt": "Não consegui concluir seu pedido nem registrar um chamado. Procure diretamente os canais de atendimento da Getnet.",
}


def escalate(
    tickets: TicketStore,
    request_id: str,
    user_id: str,
    masked_message: str,
    reason: str,
    route: list[str],
    language: str,
) -> tuple[str, str | None]:
    result = tickets.create_ticket(request_id, user_id, masked_message, reason, route, language)
    if result["status"] != "ok":
        return FAILED[language], None
    return MESSAGES[language].format(ticket_id=result["ticket_id"]), result["ticket_id"]
