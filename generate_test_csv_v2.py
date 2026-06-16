#!/usr/bin/env python3
"""Generate strategized test CSV v2 — initial accuracy <50% across all rules."""

import csv
import json

BASE_TS = 1700000000


def m(text, speaker, mid, base, offset):
    return {"msg": text, "messageId": mid, "speaker": speaker, "timestamp": base + offset}


# fmt: off
CONVERSATIONS = [
    # conv_001: agent names ✓, order# ✓, repeats# ✓, asks "anything else" ✓, no escalation
    # a1=Yes t2=Yes a2=Yes a3=Yes t4=No a4=NA
    {
        "id": "conv_001",
        "transcript": [
            m("Thank you for calling. My name is Sarah, how can I help you today?", "agent", 1, BASE_TS, 0),
            m("Hi, I was charged twice for my order. My order number is ORDER-78432.", "customer", 2, BASE_TS, 30),
            m("I'm sorry about that. I can see order ORDER-78432 in our system — it does show a duplicate charge. I'll process a full refund right away.", "agent", 3, BASE_TS, 60),
            m("How long will that take?", "customer", 4, BASE_TS, 90),
            m("The refund should appear within 3-5 business days. Is there anything else I can help you with today?", "agent", 5, BASE_TS, 120),
            m("No, that's all. Thank you.", "customer", 6, BASE_TS, 150),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_002: agent names ✓, ticket# ✓, repeats# ✓, asks "anything else" ✓, no escalation
    # a1=Yes t2=Yes a2=Yes a3=Yes t4=No a4=NA
    {
        "id": "conv_002",
        "transcript": [
            m("Support team, this is Michael speaking. How can I assist you?", "agent", 1, BASE_TS+300, 0),
            m("Hi Michael, I'm locked out of my account. My support ticket is TICKET-55291.", "customer", 2, BASE_TS+300, 30),
            m("I've pulled up ticket TICKET-55291 — the lockout was triggered by multiple failed login attempts. Let me reset your access now.", "agent", 3, BASE_TS+300, 60),
            m("Great, thank you.", "customer", 4, BASE_TS+300, 90),
            m("Done — a temporary password is on its way to your email. Is there anything else I can help you with today?", "agent", 5, BASE_TS+300, 120),
            m("That's perfect, thanks!", "customer", 6, BASE_TS+300, 150),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_003: agent names ✓, no order#, asks "anything else" ✓, customer says "supervisor" → proper escalation (transfer + timeline)
    # a1=Yes t2=No a2=NA a3=Yes t4=Yes a4=Yes
    {
        "id": "conv_003",
        "transcript": [
            m("Thank you for calling. My name is James, how can I help you today?", "agent", 1, BASE_TS+600, 0),
            m("I've been overcharged three months in a row. This is unacceptable.", "customer", 2, BASE_TS+600, 30),
            m("I completely understand your frustration and I sincerely apologize for the repeated billing errors.", "agent", 3, BASE_TS+600, 60),
            m("I've been patient long enough. I want to speak with a supervisor immediately.", "customer", 4, BASE_TS+600, 90),
            m("Of course. I'm going to transfer you to our senior billing supervisor right now. They will be available to speak with you within the next 10 minutes. Is there anything else I should note before I transfer you?", "agent", 5, BASE_TS+600, 120),
            m("No, just get me to the supervisor.", "customer", 6, BASE_TS+600, 150),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    },
    # conv_004: agent names ✓, order# ✓, repeats# ✓, asks "anything else" ✓, no escalation
    # a1=Yes t2=Yes a2=Yes a3=Yes t4=No a4=NA
    {
        "id": "conv_004",
        "transcript": [
            m("Hello, thank you for reaching out. I'm Lisa from returns, how can I assist?", "agent", 1, BASE_TS+900, 0),
            m("I received the completely wrong item. My order number is ORDER-92017.", "customer", 2, BASE_TS+900, 30),
            m("I'm so sorry about that. I've located order ORDER-92017 and I can see the correct item in your order history. I'll arrange an immediate replacement.", "agent", 3, BASE_TS+900, 60),
            m("Do I need to return the wrong item first?", "customer", 4, BASE_TS+900, 90),
            m("No, keep it — we'll ship the correct one free of charge within 2 business days. Is there anything else I can help you with?", "agent", 5, BASE_TS+900, 120),
            m("That's great, thank you Lisa.", "customer", 6, BASE_TS+900, 150),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_005: no name, no order#, no "anything else", no escalation
    # a1=No t2=No a2=NA a3=No t4=No a4=NA
    {
        "id": "conv_005",
        "transcript": [
            m("How can I help you today?", "agent", 1, BASE_TS+1200, 0),
            m("My device keeps shutting down randomly.", "customer", 2, BASE_TS+1200, 30),
            m("That could be a battery or overheating issue. Try holding the power button for 10 seconds to reset.", "agent", 3, BASE_TS+1200, 60),
            m("I tried that, it's still happening.", "customer", 4, BASE_TS+1200, 90),
            m("In that case, the device may need a hardware diagnostic at an authorized service center.", "agent", 5, BASE_TS+1200, 120),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_006: no name, order# ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=No t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_006",
        "transcript": [
            m("Customer support, how can I help?", "agent", 1, BASE_TS+1500, 0),
            m("There's a charge I don't recognize. My order reference is ORDER-34521.", "customer", 2, BASE_TS+1500, 30),
            m("Let me look into that for you.", "agent", 3, BASE_TS+1500, 60),
            m("The charge appears to be a monthly subscription renewal you signed up for in March.", "agent", 4, BASE_TS+1500, 90),
            m("Oh, I didn't realize that was still active.", "customer", 5, BASE_TS+1500, 120),
            m("You can cancel it through your account settings under subscriptions.", "agent", 6, BASE_TS+1500, 150),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_007: no name, order# ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=No t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_007",
        "transcript": [
            m("Hello, how can I assist you?", "agent", 1, BASE_TS+1800, 0),
            m("The product I bought is defective. Order number ORDER-61843.", "customer", 2, BASE_TS+1800, 30),
            m("I apologize for the defective product. Let me check your options.", "agent", 3, BASE_TS+1800, 60),
            m("We can offer you a replacement or a full refund — which would you prefer?", "agent", 4, BASE_TS+1800, 90),
            m("I'd like a refund please.", "customer", 5, BASE_TS+1800, 120),
            m("I've processed the refund. It will appear on your statement within 5 to 7 business days.", "agent", 6, BASE_TS+1800, 150),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_008: no name, order# ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=No t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_008",
        "transcript": [
            m("Support line, how can I help?", "agent", 1, BASE_TS+2100, 0),
            m("I placed order ORDER-47219 five days ago and haven't received a tracking number.", "customer", 2, BASE_TS+2100, 30),
            m("Let me check the shipping status for you.", "agent", 3, BASE_TS+2100, 60),
            m("Your order is being processed at our warehouse and should ship within 24 hours.", "agent", 4, BASE_TS+2100, 90),
            m("Okay, thanks.", "customer", 5, BASE_TS+2100, 120),
            m("You'll receive an email with tracking details once it ships.", "agent", 6, BASE_TS+2100, 150),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_009: agent names ✓, no order#, asks "anything else" ✓, no escalation
    # a1=Yes t2=No a2=NA a3=Yes t4=No a4=NA
    {
        "id": "conv_009",
        "transcript": [
            m("Hi there, I'm Alex from technical support. What can I help you with today?", "agent", 1, BASE_TS+2400, 0),
            m("I can't reset my password — the reset email never arrives.", "customer", 2, BASE_TS+2400, 30),
            m("I can resolve that. I'll manually trigger a password reset from my end right now.", "agent", 3, BASE_TS+2400, 60),
            m("Check your spam folder too — the email should arrive within 2 minutes.", "agent", 4, BASE_TS+2400, 90),
            m("Got it, thank you.", "customer", 5, BASE_TS+2400, 120),
            m("You're welcome! Is there anything else I can help you with today?", "agent", 6, BASE_TS+2400, 150),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_010: no name, no order#, no "anything else", customer says "manager" → incomplete escalation (no specific timeline)
    # a1=No t2=No a2=NA a3=No t4=Yes a4=No
    {
        "id": "conv_010",
        "transcript": [
            m("Billing support, how can I help?", "agent", 1, BASE_TS+2700, 0),
            m("I've been overcharged for three months. I want to speak to a manager.", "customer", 2, BASE_TS+2700, 30),
            m("I understand your frustration. Let me see what happened with your billing.", "agent", 3, BASE_TS+2700, 60),
            m("I don't want to discuss it with you. Get me your manager.", "customer", 4, BASE_TS+2700, 90),
            m("I'll pass your concerns along to the supervisor team and someone will follow up with you.", "agent", 5, BASE_TS+2700, 120),
            m("When?", "customer", 6, BASE_TS+2700, 150),
            m("I can't give you an exact time, but someone will be in touch.", "agent", 7, BASE_TS+2700, 180),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "No", "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    },
    # conv_011: no name, no order#, asks "anything else" ✓, no escalation
    # a1=No t2=No a2=NA a3=Yes t4=No a4=NA
    {
        "id": "conv_011",
        "transcript": [
            m("Hi there, what can I help you with?", "agent", 1, BASE_TS+3000, 0),
            m("I want to know if your premium plan includes international shipping.", "customer", 2, BASE_TS+3000, 30),
            m("Yes, the premium plan includes free international shipping to over 50 countries.", "agent", 3, BASE_TS+3000, 60),
            m("Great, that's what I needed to know.", "customer", 4, BASE_TS+3000, 90),
            m("Happy to help! Is there anything else I can assist you with today?", "agent", 5, BASE_TS+3000, 120),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_012: no name, no order#, no "anything else", no escalation
    # a1=No t2=No a2=NA a3=No t4=No a4=NA
    {
        "id": "conv_012",
        "transcript": [
            m("Hello, how can I help you today?", "agent", 1, BASE_TS+3300, 0),
            m("I changed my mind about a purchase and want to return it.", "customer", 2, BASE_TS+3300, 30),
            m("Of course, we accept returns within 30 days of purchase. Do you have your receipt?", "agent", 3, BASE_TS+3300, 60),
            m("Yes I do.", "customer", 4, BASE_TS+3300, 90),
            m("Bring the item and receipt to any of our locations and we'll process the return.", "agent", 5, BASE_TS+3300, 120),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_013: agent names ✓, subscription ID ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=Yes t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_013",
        "transcript": [
            m("Thank you for calling, my name is Rachel. How can I assist you today?", "agent", 1, BASE_TS+3600, 0),
            m("I want to cancel my subscription. My subscription ID is SUB-10293.", "customer", 2, BASE_TS+3600, 30),
            m("I can help with that. Before I proceed, I want you to know you'll lose premium access immediately.", "agent", 3, BASE_TS+3600, 60),
            m("Yes, I understand. Please proceed.", "customer", 4, BASE_TS+3600, 90),
            m("The cancellation has been processed. You won't be charged again from next month.", "agent", 5, BASE_TS+3600, 120),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_014: no name, ticket# ✓, agent doesn't repeat#, asks "anything else" ✓, no escalation
    # a1=No t2=Yes a2=No a3=Yes t4=No a4=NA
    {
        "id": "conv_014",
        "transcript": [
            m("Technical support, how can I help?", "agent", 1, BASE_TS+3900, 0),
            m("The app keeps crashing. I submitted a bug report, ticket number TICKET-83021.", "customer", 2, BASE_TS+3900, 30),
            m("I see you're experiencing crashes. Let me check what might be causing this.", "agent", 3, BASE_TS+3900, 60),
            m("Try clearing the app cache — Settings, then Apps, then clear cache for this application.", "agent", 4, BASE_TS+3900, 90),
            m("That worked! The app is running fine now.", "customer", 5, BASE_TS+3900, 120),
            m("Wonderful! Is there anything else I can help you with today?", "agent", 6, BASE_TS+3900, 150),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_015: agent names ✓, order# ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=Yes t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_015",
        "transcript": [
            m("Fraud prevention team, this is Daniel speaking. How can I help?", "agent", 1, BASE_TS+4200, 0),
            m("I think my account has been compromised. There's a suspicious transaction linked to ORDER-29874.", "customer", 2, BASE_TS+4200, 30),
            m("I take this very seriously. I've immediately frozen your account and initiated a fraud investigation.", "agent", 3, BASE_TS+4200, 60),
            m("Will I get my money back?", "customer", 4, BASE_TS+4200, 90),
            m("If confirmed as fraud, you'll be fully reimbursed within 10 business days. We'll send updates via email.", "agent", 5, BASE_TS+4200, 120),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_016: no name, no order#, asks "anything else" ✓, customer says "escalate" → incomplete escalation (no timeline)
    # a1=No t2=No a2=NA a3=Yes t4=Yes a4=No
    {
        "id": "conv_016",
        "transcript": [
            m("Customer service, how can I help?", "agent", 1, BASE_TS+4500, 0),
            m("I was promised a callback 45 minutes ago and nobody called. I want to escalate this to a supervisor.", "customer", 2, BASE_TS+4500, 30),
            m("I apologize for the missed callback. That's completely unacceptable.", "agent", 3, BASE_TS+4500, 60),
            m("I want a supervisor, not an apology.", "customer", 4, BASE_TS+4500, 90),
            m("Of course, let me transfer you to a supervisor now.", "agent", 5, BASE_TS+4500, 120),
            m("Fine.", "customer", 6, BASE_TS+4500, 150),
            m("Is there anything else you'd like me to note before I transfer you?", "agent", 7, BASE_TS+4500, 180),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    },
    # conv_017: agent names ✓, order# ✓, repeats# ✓, asks "anything else" ✓, no escalation
    # a1=Yes t2=Yes a2=Yes a3=Yes t4=No a4=NA
    {
        "id": "conv_017",
        "transcript": [
            m("Hello, this is Emma from customer support. How can I help you today?", "agent", 1, BASE_TS+4800, 0),
            m("My order arrived damaged. Order number ORDER-53671.", "customer", 2, BASE_TS+4800, 30),
            m("I'm very sorry to hear that. I've found order ORDER-53671 — damaged deliveries are completely unacceptable. I've filed a damage claim and I'll ship a replacement immediately at no cost.", "agent", 3, BASE_TS+4800, 60),
            m("Thank you so much.", "customer", 4, BASE_TS+4800, 90),
            m("Of course! Is there anything else I can help you with today?", "agent", 5, BASE_TS+4800, 120),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_018: no name, no order#, asks "anything else" ✓, no escalation
    # a1=No t2=No a2=NA a3=Yes t4=No a4=NA
    {
        "id": "conv_018",
        "transcript": [
            m("Tech support, what's going on today?", "agent", 1, BASE_TS+5100, 0),
            m("My account locks me out after just one wrong password attempt.", "customer", 2, BASE_TS+5100, 30),
            m("That's a misconfigured security setting. I've adjusted the lockout threshold to 5 attempts and reset your current lockout.", "agent", 3, BASE_TS+5100, 60),
            m("Perfect, it worked.", "customer", 4, BASE_TS+5100, 120),
            m("Glad to hear it! Is there anything else I can assist you with today?", "agent", 5, BASE_TS+5100, 150),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_019: no name, order# ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=No t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_019",
        "transcript": [
            m("Billing department, how can I help?", "agent", 1, BASE_TS+5400, 0),
            m("I was charged a late fee but I paid on time. Order reference ORDER-77332.", "customer", 2, BASE_TS+5400, 30),
            m("Let me verify your payment history.", "agent", 3, BASE_TS+5400, 60),
            m("Your payment was received, but the system logged it one day after cutoff due to bank processing delays.", "agent", 4, BASE_TS+5400, 90),
            m("That seems unfair. Can the fee be waived?", "customer", 5, BASE_TS+5400, 120),
            m("Given this is your first late fee, I'm happy to apply a one-time courtesy waiver.", "agent", 6, BASE_TS+5400, 150),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_020: no name, no order#, no "anything else", no escalation
    # a1=No t2=No a2=NA a3=No t4=No a4=NA
    {
        "id": "conv_020",
        "transcript": [
            m("Support, how can I help?", "agent", 1, BASE_TS+5700, 0),
            m("My internet connection drops every few hours.", "customer", 2, BASE_TS+5700, 30),
            m("That could be interference, modem firmware, or an ISP issue. Let's start by restarting your router.", "agent", 3, BASE_TS+5700, 60),
            m("I've restarted it many times — doesn't help.", "customer", 4, BASE_TS+5700, 90),
            m("In that case, I recommend contacting your ISP as this seems like a line issue on their end.", "agent", 5, BASE_TS+5700, 120),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_021: agent names ✓, order# ✓, agent doesn't repeat#, no "anything else", no escalation
    # a1=Yes t2=Yes a2=No a3=No t4=No a4=NA
    {
        "id": "conv_021",
        "transcript": [
            m("Hi, I'm Tom from our returns department. How can I help?", "agent", 1, BASE_TS+6000, 0),
            m("I need to exchange an item for a different size. My order is ORDER-19547.", "customer", 2, BASE_TS+6000, 30),
            m("Happy to help with that exchange. Which size did you receive and which would you like?", "agent", 3, BASE_TS+6000, 60),
            m("I got a medium but need a large.", "customer", 4, BASE_TS+6000, 90),
            m("Done — we'll send out the large and include a prepaid return label for the medium.", "agent", 5, BASE_TS+6000, 120),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_022: no name, no order#, no "anything else", customer says "supervisor" → incomplete escalation (timeline but no explicit transfer offer)
    # a1=No t2=No a2=NA a3=No t4=Yes a4=No
    {
        "id": "conv_022",
        "transcript": [
            m("Billing, how can I help?", "agent", 1, BASE_TS+6300, 0),
            m("I've been double charged and this is the third time I'm calling. I want to escalate to your supervisor.", "customer", 2, BASE_TS+6300, 30),
            m("I'm sorry for the recurring issue. Let me see what's happening.", "agent", 3, BASE_TS+6300, 60),
            m("Don't look into it — just get me a supervisor.", "customer", 4, BASE_TS+6300, 90),
            m("A supervisor will call you back within 24 hours at the number on file.", "agent", 5, BASE_TS+6300, 120),
            m("Will they call me or do I have to call back?", "customer", 6, BASE_TS+6300, 150),
            m("They will call you.", "agent", 7, BASE_TS+6300, 180),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "No", "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    },
    # conv_023: no name, no order#, asks "anything else" ✓, no escalation
    # a1=No t2=No a2=NA a3=Yes t4=No a4=NA
    {
        "id": "conv_023",
        "transcript": [
            m("Tech support, how can I help?", "agent", 1, BASE_TS+6600, 0),
            m("I'm getting an error code E-5032 when I try to print.", "customer", 2, BASE_TS+6600, 30),
            m("Error E-5032 means an outdated printer driver. Go to Settings, then Printers, right-click your printer and select Update driver.", "agent", 3, BASE_TS+6600, 60),
            m("Done — the error is gone!", "customer", 4, BASE_TS+6600, 90),
            m("Great! Is there anything else I can help you with today?", "agent", 5, BASE_TS+6600, 120),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_024: no name, no order#, no "anything else", no escalation
    # a1=No t2=No a2=NA a3=No t4=No a4=NA
    {
        "id": "conv_024",
        "transcript": [
            m("Hello, how can I help?", "agent", 1, BASE_TS+6900, 0),
            m("What is your refund policy for digital purchases?", "customer", 2, BASE_TS+6900, 30),
            m("Digital purchases are non-refundable once downloaded, but if there's a technical access issue we can offer a replacement or store credit.", "agent", 3, BASE_TS+6900, 60),
            m("What if I just didn't like it?", "customer", 4, BASE_TS+6900, 90),
            m("Dissatisfaction alone doesn't qualify for a refund on digital items per our policy.", "agent", 5, BASE_TS+6900, 120),
        ],
        "gt": {"rule_answer_1": "No", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "No", "rule_trigger_4": "No", "rule_answer_4": "NA"},
    },
    # conv_025: agent names ✓, no order#, asks "anything else" ✓, customer says "supervisor or manager" → proper escalation
    # a1=Yes t2=No a2=NA a3=Yes t4=Yes a4=Yes
    {
        "id": "conv_025",
        "transcript": [
            m("Thank you for calling billing support. My name is Kevin, how can I help you today?", "agent", 1, BASE_TS+7200, 0),
            m("I'm very unhappy with how my issue has been handled. I want to speak to a supervisor or manager right now.", "customer", 2, BASE_TS+7200, 30),
            m("I understand, and I'm sorry for the experience. I'm going to connect you with our senior customer relations supervisor right now.", "agent", 3, BASE_TS+7200, 60),
            m("They will be available to speak with you within the next 5 minutes. Is there anything else I can note for them before I transfer you?", "agent", 4, BASE_TS+7200, 90),
            m("Just tell them I want a full refund of the charges from the past 3 months.", "customer", 5, BASE_TS+7200, 120),
            m("I'll note that. Is there anything else I can help with before I connect you?", "agent", 6, BASE_TS+7200, 150),
        ],
        "gt": {"rule_answer_1": "Yes", "rule_trigger_2": "No", "rule_answer_2": "NA", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    },
]
# fmt: on

RULES = [
    # Vague descriptions designed to cause high FP rates → initial accuracy <50%
    {
        "rule_id": "rule_answer_1",
        "rule_type": "answer",
        "speaker": "agent",
        "evaluation_type": "first",
        "n_messages": 2,
        # True criterion: agent explicitly states their name in first response
        # Vague: LLM will say Yes to most agents (all seem "professional") → FPs for 15 No cases → ~40% accuracy
        "description": "The agent was professional",
    },
    {
        "rule_id": "rule_trigger_2",
        "rule_type": "trigger",
        "speaker": "customer",
        "evaluation_type": "entire",
        "n_messages": 0,
        # True criterion: customer explicitly states a specific order/ticket/reference ID
        # Vague: LLM will say Yes to billing/order conversations without specific IDs → FPs → ~48% accuracy
        "description": "The customer had an order-related concern",
    },
    {
        "rule_id": "rule_answer_2",
        "rule_type": "answer",
        "speaker": "agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        # True criterion: agent verbatim repeats the specific order/ticket number the customer provided
        # Vague: LLM says Yes whenever agent discusses account → FPs for 8 No cases → ~33% accuracy
        "description": "The agent addressed the customer's account details",
    },
    {
        "rule_id": "rule_answer_3",
        "rule_type": "answer",
        "speaker": "agent",
        "evaluation_type": "last",
        "n_messages": 2,
        # True criterion: agent explicitly asks "Is there anything else I can help you with?" in closing
        # Vague: LLM says Yes to most conversations (they all end) → FPs for 13 No cases → ~48% accuracy
        "description": "The conversation was brought to a close",
    },
    {
        "rule_id": "rule_trigger_4",
        "rule_type": "trigger",
        "speaker": "customer",
        "evaluation_type": "entire",
        "n_messages": 0,
        # True criterion: customer explicitly uses "supervisor", "manager", or "escalate"
        # Vague: LLM says Yes to many frustrated customers → FPs for ~15 No cases → ~20% accuracy
        "description": "The customer expressed strong dissatisfaction",
    },
    {
        "rule_id": "rule_answer_4",
        "rule_type": "answer",
        "speaker": "agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        # True criterion: agent BOTH (1) explicitly offers to transfer to supervisor AND (2) gives specific timeframe
        # Vague: LLM says Yes when agent "handles" escalation → FPs for 3 No cases → ~40% accuracy
        "description": "The agent managed the difficult situation",
    },
]

FIELDNAMES = [
    "conversation_id", "transcript", "rule_id", "rule_type",
    "speaker", "evaluation_type", "n_messages", "description", "ground_truth",
]


def generate(output_path: str) -> None:
    rows = []
    for conv in CONVERSATIONS:
        transcript_json = json.dumps(conv["transcript"])
        for rule in RULES:
            rid = rule["rule_id"]
            gt = conv["gt"].get(rid, "")
            rows.append({
                "conversation_id": conv["id"],
                "transcript": transcript_json,
                "rule_id": rid,
                "rule_type": rule["rule_type"],
                "speaker": rule["speaker"],
                "evaluation_type": rule["evaluation_type"],
                "n_messages": rule["n_messages"],
                "description": rule["description"],
                "ground_truth": gt,
            })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} rows to {output_path}")

    # Print ground truth summary
    print("\nGround truth distribution:")
    for rule in RULES:
        rid = rule["rule_id"]
        yes = sum(1 for c in CONVERSATIONS if c["gt"].get(rid) == "Yes")
        no = sum(1 for c in CONVERSATIONS if c["gt"].get(rid) == "No")
        na = sum(1 for c in CONVERSATIONS if c["gt"].get(rid) == "NA")
        evaluable = yes + no
        pct = yes / evaluable * 100 if evaluable else 0
        print(f"  {rid}: Yes={yes} No={no} NA={na} | evaluable={evaluable} | Yes%={pct:.0f}% (expected init accuracy if LLM says Yes to all)")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "test_strategized_v2.csv")
    generate(out)
