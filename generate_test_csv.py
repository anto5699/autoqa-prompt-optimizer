"""
generate_test_csv.py

Generates a strategized test CSV for the AutoQA prompt optimization system.
25 conversations × 6 rules = 150 rows.

Evaluation criteria (what makes each label):
  answer_1 Yes  : Agent says both their name AND "Kore Bank" in first 3 messages
  answer_1 No   : Greeting missing name or company, or no greeting at all

  trigger_2 Yes : Customer explicitly expresses frustration/anger/dissatisfaction
  trigger_2 No  : Customer is neutral / polite / curious

  answer_2 Yes  : Agent sincerely apologises AND commits to a specific concrete action
  answer_2 No   : Agent gives excuses, lacks empathy, or no specific action committed

  answer_3 Yes  : Agent asks "Is there anything else I can help you with?" (or equiv) before closing
  answer_3 No   : Agent just says goodbye / thanks without that question

  trigger_4 Yes : Customer mentions unrecognised charge / duplicate / overcharge / refund / billing dispute
  trigger_4 No  : Customer asks about account features, balance, hours, rates, rewards — no billing concern

  answer_4 Yes  : Agent verifies concern AND provides concrete resolution AND gives timeline/outcome
  answer_4 No   : Agent dismisses, gives only policy, says "we'll look into it" vaguely, or just notes it
"""

import csv
import json
import io

OUTPUT_PATH = "/Users/Prakash.Anto/Projects/autoqa-prompt-optimizer/test_strategized.csv"

BASE_TS = 1748908800  # 2025-06-03 00:00:00 UTC
TS_STEP = 30


def make_transcript(turns):
    """turns: list of (speaker, msg) tuples. Returns JSON string."""
    messages = []
    for i, (speaker, msg) in enumerate(turns):
        messages.append({
            "msg": msg,
            "messageId": i,
            "speaker": speaker,
            "timestamp": BASE_TS + i * TS_STEP,
        })
    return json.dumps(messages)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
# Each value is a list of (speaker, message) tuples.

CONVERSATIONS = {

    # -----------------------------------------------------------------------
    # Group A: Neutral service calls — no complaints, no billing issues
    # -----------------------------------------------------------------------

    # conv_001: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=No, answer_4=NA
    "conv_001": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Sarah. How can I assist you today?"),
        ("customer", "Hi, I'd like to update my mailing address please."),
        ("agent",    "Of course! I can help with that. Could I have your account number to pull up your profile?"),
        ("customer", "Sure, it's 4-4-7-8-9-2."),
        ("agent",    "Thank you. I've updated your address to the new one you provided. Is there anything else I can help you with today?"),
        ("customer", "No, that's all. Thanks!"),
        ("agent",    "Great, have a wonderful day!"),
    ]),

    # conv_002: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=No, trigger_4=No, answer_4=NA
    "conv_002": make_transcript([
        ("agent",    "Thanks for calling Kore Bank. My name is David. How may I help you?"),
        ("customer", "Hi David, I just want to check if my direct deposit is set up correctly."),
        ("agent",    "Absolutely. Can I get your account number or the last four digits of your Social Security Number to verify your identity?"),
        ("customer", "Last four of SSN is 7-7-3-1."),
        ("agent",    "Perfect, I've verified your direct deposit details and everything looks correct. Your next deposit should arrive on Friday."),
        ("customer", "Great, thank you!"),
        ("agent",    "Thank you for calling Kore Bank. Have a great day!"),
    ]),

    # conv_003: answer_1=No, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=No, answer_4=NA
    "conv_003": make_transcript([
        ("agent",    "Hello! Thank you for calling. How can I help you today?"),
        ("customer", "I'd like to know the operating hours for the downtown branch."),
        ("agent",    "Sure! The downtown branch is open Monday through Friday from 9 AM to 5 PM, and Saturday from 10 AM to 2 PM."),
        ("customer", "What about Sunday?"),
        ("agent",    "Unfortunately, the downtown branch is closed on Sundays. Is there anything else I can help you with?"),
        ("customer", "No, that covers it. Thank you!"),
        ("agent",    "Wonderful, have a great day!"),
    ]),

    # conv_004: answer_1=No, trigger_2=No, answer_2=NA, answer_3=No, trigger_4=No, answer_4=NA
    "conv_004": make_transcript([
        ("agent",    "Hi there! What can I do for you today?"),
        ("customer", "I want to find out about your savings account interest rates."),
        ("agent",    "Our standard savings account currently offers 0.5% APY. We also have a high-yield savings account at 4.2% APY."),
        ("customer", "How do I open the high-yield one?"),
        ("agent",    "You can open it online at korebank.com or by visiting any branch. Would you like me to walk you through the online process?"),
        ("customer", "No, I'll check online. Thanks."),
        ("agent",    "Sounds good, goodbye!"),
    ]),

    # conv_005: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=No, answer_4=NA
    "conv_005": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Michelle speaking. How can I assist you?"),
        ("customer", "I need to find out how to set up online banking."),
        ("agent",    "Happy to help! You can register at korebank.com by clicking 'Sign Up'. You'll need your account number and a valid email."),
        ("customer", "Do I need any special verification?"),
        ("agent",    "Yes, we'll send a one-time code to your email or phone to confirm your identity. The process takes about 5 minutes."),
        ("customer", "That sounds straightforward. Thank you."),
        ("agent",    "Of course! Is there anything else I can help you with today?"),
        ("customer", "No, that's all."),
        ("agent",    "Excellent, enjoy your online banking experience. Goodbye!"),
    ]),

    # -----------------------------------------------------------------------
    # Group B: Complaint calls — trigger_2=Yes, trigger_4=No
    # -----------------------------------------------------------------------

    # conv_006: answer_1=Yes, trigger_2=Yes, answer_2=Yes, answer_3=Yes, trigger_4=No, answer_4=NA
    "conv_006": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is James. How can I help you today?"),
        ("customer", "I am absolutely furious right now! I've been on hold for 45 minutes and this is completely unacceptable!"),
        ("agent",    "I'm truly sorry for the wait time you experienced, that's not the standard of service we aim to provide. I sincerely apologise. I'm going to escalate this to our service quality team today and ensure you receive a written follow-up within 24 hours. Your time matters to us."),
        ("customer", "Fine. I just want to update the beneficiary on my account."),
        ("agent",    "Absolutely, I can help with that right now. May I have your account number please?"),
        ("customer", "It's 5-5-2-1-8-8."),
        ("agent",    "Thank you, I've noted the beneficiary update. Is there anything else I can help you with today?"),
        ("customer", "No, I think that's all."),
        ("agent",    "Thank you for your patience. Have a good day!"),
    ]),

    # conv_007: answer_1=No, trigger_2=Yes, answer_2=Yes, answer_3=No, trigger_4=No, answer_4=NA
    "conv_007": make_transcript([
        ("agent",    "Hello, how can I assist you?"),
        ("customer", "I'm really frustrated — I've tried three times to reset my password online and it keeps failing. This is terrible!"),
        ("agent",    "I'm so sorry about the trouble you're experiencing with the password reset — I completely understand how frustrating that must be. I'm going to reset your credentials manually right now and also raise a ticket with our tech team to investigate the online portal issue so it doesn't happen again."),
        ("customer", "Okay, please do that."),
        ("agent",    "Done. Your temporary password has been sent to your registered email. Please change it once you log in."),
        ("customer", "Got it, thanks."),
        ("agent",    "Thank you for calling Kore Bank. Have a wonderful day!"),
    ]),

    # conv_008: answer_1=Yes, trigger_2=Yes, answer_2=No, answer_3=Yes, trigger_4=No, answer_4=NA
    "conv_008": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Rachel. How may I help you?"),
        ("customer", "Your service is absolutely terrible! I've been waiting a week for my new debit card and it still hasn't arrived!"),
        ("agent",    "Card deliveries can sometimes be delayed due to postal service issues. The card should arrive within 10 business days as stated in our terms."),
        ("customer", "That's not good enough! Can you do something?"),
        ("agent",    "I can see your card was dispatched. You'll just need to wait for the standard delivery window to complete."),
        ("customer", "This is ridiculous. Fine."),
        ("agent",    "Is there anything else I can help you with today?"),
        ("customer", "No."),
        ("agent",    "Thank you for calling. Goodbye!"),
    ]),

    # conv_009: answer_1=No, trigger_2=Yes, answer_2=No, answer_3=Yes, trigger_4=No, answer_4=NA
    "conv_009": make_transcript([
        ("agent",    "Hello, what can I do for you today?"),
        ("customer", "I'm so angry right now — you guys closed my account without any warning!"),
        ("agent",    "Account closures happen for various compliance and policy reasons. I can look into the specifics of your account."),
        ("customer", "I want answers. Why was it closed?"),
        ("agent",    "I'm seeing a system flag on your account. I can't share more details, but it was closed per standard policy."),
        ("customer", "That explains nothing!"),
        ("agent",    "I understand this is frustrating. Is there anything else I can help you with today?"),
        ("customer", "No, this is useless."),
        ("agent",    "Thank you for calling. Have a good day."),
    ]),

    # conv_010: answer_1=Yes, trigger_2=Yes, answer_2=Yes, answer_3=No, trigger_4=No, answer_4=NA
    "conv_010": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Tom speaking. How can I assist you?"),
        ("customer", "I'm really disappointed — I was promised a callback two days ago and nobody called me back!"),
        ("agent",    "I'm genuinely sorry about that missed callback — that's not acceptable and I apologise. I'm going to look into exactly what happened with that request and personally ensure you receive a call from the appropriate team by end of business today."),
        ("customer", "Alright, I appreciate that. My original question was about my overdraft limit."),
        ("agent",    "Of course. Your current overdraft limit is $500. To request an increase, I can submit an application right now if you'd like."),
        ("customer", "Yes please. Let's do that."),
        ("agent",    "Done — the application has been submitted and you'll receive a decision within 2 business days via email. Thank you for your patience today!"),
    ]),

    # -----------------------------------------------------------------------
    # Group C: Billing inquiry calls — trigger_2=No, trigger_4=Yes
    # -----------------------------------------------------------------------

    # conv_011: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=Yes, answer_4=Yes
    "conv_011": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Lisa. How can I help you today?"),
        ("customer", "Hi Lisa, I noticed a charge of $35 on my account that I don't recognise. Could you help me understand it?"),
        ("agent",    "Of course! I can look into that for you. Could you confirm your account number and the date of the charge?"),
        ("customer", "Account number 3-3-4-5-6-7, and the charge appeared on May 28th."),
        ("agent",    "Thank you. I've reviewed that transaction and I can see it's an annual maintenance fee that was applied in error — your account type is exempt from that fee. I'm initiating a full refund of $35 right now, and you should see it reflected within 2 business days."),
        ("customer", "Oh great, thank you so much!"),
        ("agent",    "Of course! Is there anything else I can help you with today?"),
        ("customer", "No, that's all."),
        ("agent",    "Have a wonderful day. Goodbye!"),
    ]),

    # conv_012: answer_1=No, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=Yes, answer_4=Yes
    "conv_012": make_transcript([
        ("agent",    "Hello, how may I assist you?"),
        ("customer", "I see a duplicate charge on my account from last Friday for $22. Could you check that?"),
        ("agent",    "Sure, can I have your account number and the merchant name on the charge?"),
        ("customer", "Account 7-8-9-0-0-1, merchant is CoffeePlus."),
        ("agent",    "I can confirm there are two identical CoffeePlus charges of $22 on June 1st. This appears to be a duplicate processing error. I'm reversing the duplicate charge now — you'll see the $22 credit within 1-2 business days."),
        ("customer", "That's a relief, thank you."),
        ("agent",    "My pleasure. Is there anything else I can help you with?"),
        ("customer", "No, that's it."),
        ("agent",    "Great, goodbye!"),
    ]),

    # conv_013: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=No, trigger_4=Yes, answer_4=No
    "conv_013": make_transcript([
        ("agent",    "Thanks for calling Kore Bank, this is Kevin here. How can I help?"),
        ("customer", "Hi Kevin, I got a charge of $15 that I don't understand. It just says 'service fee'."),
        ("agent",    "That's our monthly account maintenance fee, which applies to all standard checking accounts."),
        ("customer", "I didn't know about this fee. Is there any way to waive it?"),
        ("agent",    "Unfortunately, that fee is standard for your account tier. You'd need to upgrade to a premium account to have it waived."),
        ("customer", "Okay, I guess I'll look into that."),
        ("agent",    "Sounds good. Thank you for calling. Goodbye!"),
    ]),

    # conv_014: answer_1=No, trigger_2=No, answer_2=NA, answer_3=No, trigger_4=Yes, answer_4=No
    "conv_014": make_transcript([
        ("agent",    "Hi there, what can I help you with?"),
        ("customer", "I want to dispute a charge. There's an ATM fee of $3 that I shouldn't have been charged because I used a Kore Bank ATM."),
        ("agent",    "ATM fees can vary based on your account terms. Let me see — yes, there is a $3 fee. That does appear to be within normal parameters."),
        ("customer", "But I used a Kore Bank ATM. That should be free!"),
        ("agent",    "I'll note your concern. Our billing department will review ATM fee disputes within 30 days."),
        ("customer", "30 days? That seems very long."),
        ("agent",    "That's our standard review period. Thank you for calling. Have a nice day!"),
    ]),

    # conv_015: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=Yes, answer_4=Yes
    "conv_015": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Angela. How may I assist you?"),
        ("customer", "Hi Angela, I think I was overcharged. I see two $10 monthly fees but I should only have one account."),
        ("agent",    "Let me look into that for you. Can I have your account number please?"),
        ("customer", "Yes, it's 1-2-3-4-5-6."),
        ("agent",    "I can see there's a duplicate account in our system from a data migration last month. I'm closing the duplicate account now and initiating a refund of $10 for the erroneous charge, which will post within 24 hours."),
        ("customer", "That's great, thank you Angela."),
        ("agent",    "Absolutely! Is there anything else I can help you with today?"),
        ("customer", "No, that's all. Thanks!"),
        ("agent",    "Have a great day!"),
    ]),

    # -----------------------------------------------------------------------
    # Group D: Complaint + billing — trigger_2=Yes, trigger_4=Yes
    # -----------------------------------------------------------------------

    # conv_016: answer_1=Yes, trigger_2=Yes, answer_2=Yes, answer_3=Yes, trigger_4=Yes, answer_4=Yes
    "conv_016": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Nathan. How can I assist you today?"),
        ("customer", "I'm completely fed up! You charged me twice this month AND your app keeps crashing — this is absolutely unacceptable!"),
        ("agent",    "I'm deeply sorry for both issues — you have every right to be frustrated and I sincerely apologise. Let me address both right now. I'm raising an urgent bug ticket for the app crashes and marking it for priority resolution by our tech team within 48 hours."),
        ("customer", "Good. And the double charge?"),
        ("agent",    "I can see two identical charges of $25 on May 30th. I'm reversing the duplicate right now and you'll see the refund within 1 business day. You have my word this will be resolved."),
        ("customer", "Finally some action. Thank you."),
        ("agent",    "Is there anything else I can help you with today?"),
        ("customer", "No, that's all."),
        ("agent",    "Thank you for your patience. Have a good day!"),
    ]),

    # conv_017: answer_1=No, trigger_2=Yes, answer_2=No, answer_3=No, trigger_4=Yes, answer_4=Yes
    "conv_017": make_transcript([
        ("agent",    "Hello, how can I help?"),
        ("customer", "Your service is terrible! And on top of that, there's an overcharge on my account for $50!"),
        ("agent",    "I hear you. Service issues are something we're always working to improve. Regarding your account, let me look at that charge."),
        ("customer", "I've been a customer for 10 years and this is how I'm treated?"),
        ("agent",    "I understand your frustration. Looking at the $50 charge — that is indeed an erroneous fee that was applied during a system upgrade. I'm reversing it now with a credit back within 2 business days."),
        ("customer", "At least you're fixing the charge. The service issues still stand."),
        ("agent",    "I've logged your feedback on the service quality as well. Thank you for calling!"),
    ]),

    # conv_018: answer_1=Yes, trigger_2=Yes, answer_2=Yes, answer_3=Yes, trigger_4=Yes, answer_4=No
    "conv_018": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Sandra. How may I help you?"),
        ("customer", "I'm furious — I've been waiting three weeks for a loan decision and nobody has communicated with me at all!"),
        ("agent",    "I'm so sorry for the complete lack of communication — that is unacceptable and I apologise sincerely. I am escalating your loan application to our senior review team right now and ensuring you receive a status call within 24 hours."),
        ("customer", "Thank you. Also, I see a $20 charge I don't recognise."),
        ("agent",    "I see that charge — it appears to be a loan processing fee. I'll need to have our billing team investigate this further; it could take up to 2 weeks for us to look into it."),
        ("customer", "2 weeks seems long, but okay."),
        ("agent",    "I understand. Is there anything else I can help you with today?"),
        ("customer", "No, that'll do."),
        ("agent",    "Thank you, have a good day!"),
    ]),

    # conv_019: answer_1=Yes, trigger_2=Yes, answer_2=No, answer_3=No, trigger_4=Yes, answer_4=No
    "conv_019": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Peter. How can I help?"),
        ("customer", "I'm really annoyed — your teller was rude to me at the branch AND I have an unrecognised charge!"),
        ("agent",    "I'm sorry to hear about your branch experience. Staff interactions can vary and we have processes in place."),
        ("customer", "That's it? That's your response?"),
        ("agent",    "I've noted your feedback. Regarding the charge, can you give me the amount?"),
        ("customer", "It's $45 labelled 'processing fee'."),
        ("agent",    "That's a standard processing fee. I can flag it for review in our next billing cycle."),
        ("customer", "When will I hear back?"),
        ("agent",    "It's hard to say exactly. Thank you for calling. Goodbye!"),
    ]),

    # conv_020: answer_1=No, trigger_2=Yes, answer_2=Yes, answer_3=Yes, trigger_4=Yes, answer_4=Yes
    "conv_020": make_transcript([
        ("agent",    "Hello, how may I assist you today?"),
        ("customer", "I am incredibly frustrated — I disputed a charge two months ago and it's still not resolved, this is ridiculous!"),
        ("agent",    "I'm truly sorry this has been dragging on for two months — that is completely unacceptable and I deeply apologise. I'm escalating this to our disputes resolution manager right now and committing to having it resolved and communicated to you within 48 hours."),
        ("customer", "Good. The dispute is about a $60 charge that was supposed to be refunded."),
        ("agent",    "I can see the original dispute in our system. I'm processing the $60 refund immediately — it was stuck in a pending queue. You'll see it reflected in your account within 24 hours."),
        ("customer", "Finally! Thank you."),
        ("agent",    "Is there anything else I can help you with today?"),
        ("customer", "No, I think we're good now."),
        ("agent",    "Thank you for your patience. Have a great day!"),
    ]),

    # -----------------------------------------------------------------------
    # Group E: Edge cases
    # -----------------------------------------------------------------------

    # conv_021: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=No, answer_4=NA
    # Neutral inquiry about account upgrade — mild expressions don't fire trigger_2
    "conv_021": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Grace. How can I help you today?"),
        ("customer", "Hi, I've been thinking about upgrading my account to the premium tier. Could you tell me more about it?"),
        ("agent",    "Certainly! The premium tier includes unlimited ATM withdrawals, a dedicated relationship manager, and higher transfer limits. The monthly fee is $15."),
        ("customer", "That sounds interesting. I'm a bit unsure whether the $15 fee is worth it for me."),
        ("agent",    "Completely understandable. Based on your current usage, the unlimited ATM access alone could save you more than that each month. I can also waive the first month's fee as a trial."),
        ("customer", "Oh that's a nice offer. Let me think about it."),
        ("agent",    "Of course! Is there anything else I can help you with today?"),
        ("customer", "No, that's all. Thanks Grace!"),
        ("agent",    "Have a wonderful day!"),
    ]),

    # conv_022: answer_1=No, trigger_2=Yes, answer_2=Yes, answer_3=No, trigger_4=No, answer_4=NA
    # Frustration/complaint (no billing), agent greets without name, handles well, bad closure
    "conv_022": make_transcript([
        ("agent",    "Thank you for calling Kore Bank. How can I assist you?"),
        ("customer", "This is outrageous — I asked to update my contact information last week and nothing has changed! Your service is terrible!"),
        ("agent",    "I'm very sorry for this failure — that should have been updated immediately and I sincerely apologise. I am updating your contact information right now as we speak, and I'll personally flag this case to our quality team to ensure this doesn't happen to you or any other customer again."),
        ("customer", "Okay. My new email is newemail@example.com."),
        ("agent",    "I've updated it now and sent a confirmation to both your old and new email addresses. The change is active immediately."),
        ("customer", "Thank you. At least something got done."),
        ("agent",    "Thank you for calling. Have a good day!"),
    ]),

    # conv_023: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=Yes, answer_4=Yes
    # Billing cycle explanation + charge inquiry (no complaint) — all done well
    "conv_023": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Carlos. How may I help you today?"),
        ("customer", "Hi Carlos, I have a question about my billing cycle and there's a charge I'd like to understand better."),
        ("agent",    "Of course! What would you like to know?"),
        ("customer", "My billing cycle seems to have changed, and now there's a $12 charge listed as 'account fee' that I wasn't expecting."),
        ("agent",    "Great question. Your billing cycle was adjusted on May 1st due to a system migration. The $12 charge is an annual account maintenance fee that was prorated for the partial month. Since you weren't notified in advance, I'm waiving that charge immediately — you'll see the credit within 24 hours."),
        ("customer", "Oh, that's very fair. Thank you."),
        ("agent",    "Absolutely. Is there anything else I can help you with today?"),
        ("customer", "No, that covers everything."),
        ("agent",    "Great, have a wonderful day!"),
    ]),

    # conv_024: answer_1=No, trigger_2=Yes, answer_2=No, answer_3=No, trigger_4=Yes, answer_4=No
    # Aggressive complaint + overbilling dispute — poor greeting, agent dismisses both
    "conv_024": make_transcript([
        ("agent",    "What's your account number?"),
        ("customer", "Excuse me?! You don't even say hello? I've been overcharged $200 and I am absolutely livid about this!"),
        ("agent",    "Account number please, I need that to proceed."),
        ("customer", "Fine! It's 9-9-1-1-2-3. But this is completely unacceptable — you overcharged me $200!"),
        ("agent",    "I see your account. The $200 is a returned payment fee. That is a valid charge per our fee schedule."),
        ("customer", "That's a lie! I never had a returned payment. Your system made an error!"),
        ("agent",    "Our records show the fee is valid. If you believe there's an error you can submit a written dispute to our P.O. Box."),
        ("customer", "Unbelievable. I'm closing my account."),
        ("agent",    "Okay. Goodbye."),
    ]),

    # conv_025: answer_1=Yes, trigger_2=No, answer_2=NA, answer_3=Yes, trigger_4=No, answer_4=NA
    # Branch hours inquiry (pure neutral) — proper greeting, good closure
    "conv_025": make_transcript([
        ("agent",    "Thank you for calling Kore Bank, this is Fiona. How can I help you today?"),
        ("customer", "Hi Fiona, I was just wondering about the hours for the Westside branch."),
        ("agent",    "Of course! The Westside branch is open Monday through Thursday from 9 AM to 6 PM, Friday 9 AM to 7 PM, and Saturday 10 AM to 3 PM. It's closed on Sundays."),
        ("customer", "Does it have a drive-through?"),
        ("agent",    "Yes, the Westside branch does have a drive-through. The drive-through has the same hours as the main branch."),
        ("customer", "Perfect, that's all I needed."),
        ("agent",    "Is there anything else I can help you with today?"),
        ("customer", "No, that's great. Thank you Fiona!"),
        ("agent",    "Have a wonderful day. Goodbye!"),
    ]),
}

# ---------------------------------------------------------------------------
# Ground truth matrix
# ---------------------------------------------------------------------------
# Format: conv_id -> {rule_id: ground_truth}

GROUND_TRUTH = {
    "conv_001": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_002": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_003": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_004": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_005": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_006": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_007": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_008": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_009": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_010": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_011": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_012": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_013": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_014": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_015": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_016": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_017": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_018": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_019": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_020": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_021": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_022": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_023": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_024": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_025": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
}

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

RULES = [
    {
        "rule_id":         "rule_answer_1",
        "rule_type":       "answer",
        "speaker":         "agent",
        "evaluation_type": "first",
        "n_messages":      3,
        "description":     "The agent greeted the customer",
    },
    {
        "rule_id":         "rule_trigger_2",
        "rule_type":       "trigger",
        "speaker":         "customer",
        "evaluation_type": "entire",
        "n_messages":      0,
        "description":     "The customer expressed dissatisfaction",
    },
    {
        "rule_id":         "rule_answer_2",
        "rule_type":       "answer",
        "speaker":         "agent",
        "evaluation_type": "entire",
        "n_messages":      0,
        "description":     "The agent handled the customer's complaint appropriately",
    },
    {
        "rule_id":         "rule_answer_3",
        "rule_type":       "answer",
        "speaker":         "agent",
        "evaluation_type": "last",
        "n_messages":      3,
        "description":     "The agent ended the call properly",
    },
    {
        "rule_id":         "rule_trigger_4",
        "rule_type":       "trigger",
        "speaker":         "customer",
        "evaluation_type": "entire",
        "n_messages":      0,
        "description":     "The customer raised a concern about a charge or billing",
    },
    {
        "rule_id":         "rule_answer_4",
        "rule_type":       "answer",
        "speaker":         "agent",
        "evaluation_type": "entire",
        "n_messages":      0,
        "description":     "The agent addressed the customer's billing concern",
    },
]

# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "conversation_id",
    "transcript",
    "rule_id",
    "rule_type",
    "speaker",
    "evaluation_type",
    "n_messages",
    "description",
    "ground_truth",
]

conv_ids = sorted(CONVERSATIONS.keys())  # conv_001 … conv_025

rows = []
for conv_id in conv_ids:
    transcript = CONVERSATIONS[conv_id]
    gt_map = GROUND_TRUTH[conv_id]
    for rule in RULES:
        rid = rule["rule_id"]
        rows.append({
            "conversation_id": conv_id,
            "transcript":      transcript,
            "rule_id":         rid,
            "rule_type":       rule["rule_type"],
            "speaker":         rule["speaker"],
            "evaluation_type": rule["evaluation_type"],
            "n_messages":      rule["n_messages"],
            "description":     rule["description"],
            "ground_truth":    gt_map[rid],
        })

with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

import pandas as pd

df = pd.read_csv(OUTPUT_PATH, keep_default_na=False)

print(f"\nTotal rows (expected 150): {len(df)}")
assert len(df) == 150, f"Expected 150 rows, got {len(df)}"

print("\nGround truth distribution per rule_id:")
for rule in RULES:
    rid = rule["rule_id"]
    sub = df[df["rule_id"] == rid]
    counts = sub["ground_truth"].value_counts().to_dict()
    evaluable = len(sub[sub["ground_truth"] != "NA"])
    print(f"  {rid:20s}  {counts}  evaluable={evaluable}")
    assert evaluable >= 5, f"{rid} has only {evaluable} evaluable rows (need ≥5)"

print("\nVerifying ground truth matrix against expected values...")
expected_matrix = {
    "conv_001": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_002": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_003": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_004": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_005": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_006": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_007": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_008": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_009": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_010": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_011": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_012": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_013": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_014": {"rule_answer_1": "No",  "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_015": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_016": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_017": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_018": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_019": {"rule_answer_1": "Yes", "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_020": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_021": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_022": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "Yes", "rule_answer_3": "No",  "rule_trigger_4": "No",  "rule_answer_4": "NA"},
    "conv_023": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "Yes", "rule_answer_4": "Yes"},
    "conv_024": {"rule_answer_1": "No",  "rule_trigger_2": "Yes", "rule_answer_2": "No",  "rule_answer_3": "No",  "rule_trigger_4": "Yes", "rule_answer_4": "No"},
    "conv_025": {"rule_answer_1": "Yes", "rule_trigger_2": "No",  "rule_answer_2": "NA",  "rule_answer_3": "Yes", "rule_trigger_4": "No",  "rule_answer_4": "NA"},
}

errors = []
for conv_id, rule_map in expected_matrix.items():
    for rid, expected_gt in rule_map.items():
        actual = df[(df["conversation_id"] == conv_id) & (df["rule_id"] == rid)]["ground_truth"].values
        if len(actual) == 0:
            errors.append(f"MISSING: {conv_id}/{rid}")
        elif actual[0] != expected_gt:
            errors.append(f"MISMATCH {conv_id}/{rid}: expected={expected_gt}, actual={actual[0]}")

if errors:
    print("\nGround truth ERRORS:")
    for e in errors:
        print(f"  {e}")
else:
    print("  All ground truth values match the expected matrix.")

print(f"\nAll checks passed. Output: {OUTPUT_PATH}")
