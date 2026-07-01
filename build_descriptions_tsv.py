"""Build a TSV of structured input descriptions for the AutoQA prompt optimisation tool.
Columns: parameter_name<TAB>parameter_description
Each description follows the tool's required structured format (starts with METRIC_NAME:),
so the baseline_prompt_generator detects it as already-structured and leaves it unchanged.
"""
import csv

# Canonical parameter names exactly as they appear in the source sheet (en-dash preserved).
DESCRIPTIONS = {
"Acknowledgement": """METRIC_NAME: Acknowledgement
SPEAKER: Agent
ACTION: Verbally acknowledge the customer's stated concern before moving to resolution.
PASS_LOGIC: ANY
PASS_CRITERIA:
1. The agent restates, paraphrases, or repeats back the customer's reason for calling.
2. The agent uses an explicit acknowledgement phrase that references the concern (e.g. "I understand you want to ...", "ji zaroor", "samajh sakta hoon").
EXAMPLES:
PASS:
1. "I understand your credit card PIN is not generating, let me check that for you."
2. "Ji zaroor maam, aapka EMI close karna hai, main dekh leta hoon."
FAIL:
1. "Account number bataiye." (jumps to data collection without referencing the concern)
2. "Okay." (no reference to the customer's stated issue)
""",

"Appropriate_Closer": """METRIC_NAME: Appropriate Closer
SPEAKER: Agent
ACTION: Close the conversation using the required closing elements before the call ends.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent asks whether the customer needs any further assistance.
2. The agent thanks the customer for calling and names the brand (e.g. "Thank you for calling Axis Bank").
EXAMPLES:
PASS:
1. "Is there anything else I can help you with? Thank you for calling Axis Bank, have a good day."
2. "Aur koi sahayata chahiye? Axis Bank ko call karne ke liye dhanyavad."
FAIL:
1. "Have a great day." (no further-assistance check and no brand thanks)
2. (call ends with no closing statement from the agent)
""",

"Avoiding rude or demeaning language": """METRIC_NAME: Avoiding Rude Language
SPEAKER: Agent
ACTION: Refrain from using rude, dismissive, or demeaning language toward the customer.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent uses no insulting, mocking, or belittling words directed at the customer.
2. The agent does not blame, scold, or speak dismissively to the customer.
EXAMPLES:
PASS:
1. "I completely understand, let me help you sort this out."
2. "Koi baat nahi, main aapki puri madad karta hoon."
FAIL:
1. "Why don't you just listen to what I am saying?"
2. "Aapko itni si baat samajh nahi aa rahi."
""",

"Displays confidence": """METRIC_NAME: Displays Confidence
SPEAKER: Agent
ACTION: Convey the response in a confident, assured manner without uncertainty markers.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent avoids hesitation fillers and uncertainty phrases such as "might be", "maybe", "you know", "I think".
2. The agent does not express inability or refusal in an abrupt way (e.g. "I won't be able to help you").
EXAMPLES:
PASS:
1. "Yes, I can certainly help you reset the PIN right now."
2. "Bilkul, main abhi aapke liye yeh process complete kar deta hoon."
FAIL:
1. "Umm, might be, you know, I am not really sure."
2. "I won't be able to help you with this."
""",

"Double Negatives": """METRIC_NAME: Double Negatives
SPEAKER: Agent
ACTION: Evaluate whether the agent's English sentences are free of double-negative constructions.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. No agent sentence combines two negatives that cancel or confuse the meaning (e.g. "don't have no").
2. Negation in each sentence is expressed once and unambiguously.
EXAMPLES:
PASS:
1. "I don't have any pending requests on your account."
2. "There is no charge on this transaction."
FAIL:
1. "I don't have no information about that."
2. "We can't do nothing until the form is submitted."
""",

"Hold Guidelines_PostHold": """METRIC_NAME: Post Hold Guideline
SPEAKER: Agent
ACTION: Thank the customer for waiting when resuming the conversation after a hold.
PASS_LOGIC: ANY
PASS_CRITERIA:
1. On returning from hold the agent thanks the customer for holding or waiting.
2. The agent acknowledges the wait before continuing with the resolution.
EXAMPLES:
PASS:
1. "Thank you so much for holding, I have the details now."
2. "Hold karne ke liye dhanyavad, maine aapki request check kar li hai."
FAIL:
1. "So as I was saying, the amount is blocked." (resumes with no thanks for waiting)
2. "Okay it is done." (returns from hold with no acknowledgement of the wait)
""",

"Hold Guidelines_Pre Hold": """METRIC_NAME: Pre Hold Guideline
SPEAKER: Agent
ACTION: Request the customer's permission and give a reason before placing the call on hold.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent asks the customer's permission before initiating the hold.
2. The agent states a reason for the hold or how long it may take.
EXAMPLES:
PASS:
1. "May I place your call on hold for two minutes while I check this?"
2. "Main aapka call do minute hold par rakh sakta hoon? Main details verify kar leta hoon."
FAIL:
1. "Please hold." (no permission requested and no reason given)
2. (agent goes silent / dead air without informing or asking the customer)
""",

"Incorrect Plural Forms": """METRIC_NAME: Incorrect Plural Forms
SPEAKER: Agent
ACTION: Evaluate whether the agent uses correct singular and plural noun forms in English speech.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. Countable nouns are pluralised correctly when referring to more than one.
2. No singular noun is incorrectly pluralised and no plural noun is incorrectly left singular.
EXAMPLES:
PASS:
1. "You have two active credit cards on this profile."
2. "Please share the last four digits of your card."
FAIL:
1. "You have two credit card on this profile."
2. "Please share the detail of your account." (should be "details")
""",

"Jargons / Slangs": """METRIC_NAME: Jargons Or Slangs
SPEAKER: Agent
ACTION: Evaluate whether the agent avoids internal jargon, abbreviations, and slang with the customer.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent does not use internal banking jargon or system codes the customer would not understand.
2. The agent does not use casual slang in place of professional language.
EXAMPLES:
PASS:
1. "Your request will be processed within two working days."
2. "Main aapka request raise kar deta hoon, do din mein update mil jayega."
FAIL:
1. "I'll raise a SR in the CRM and tag it to the LOB."
2. "Yeah no worries dude, chill, it's sorted."
""",

"Missing Articles": """METRIC_NAME: Missing Articles
SPEAKER: Agent
ACTION: Evaluate whether the agent includes required articles (a, an, the) in English sentences.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The definite article "the" is present where grammatically required.
2. The indefinite article "a" or "an" is present and correctly chosen where required.
EXAMPLES:
PASS:
1. "Please enter the PIN for the credit card."
2. "There is an issue with the account number you shared."
FAIL:
1. "Please enter PIN for credit card." (missing "the")
2. "There is issue with account number." (missing "an"/"the")
""",

"NPS Script": """METRIC_NAME: NPS Script
SPEAKER: Agent
ACTION: Pitch the post-call NPS survey using the prescribed script wording.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent invites the customer to stay on the line for or rate a short feedback survey.
2. The agent uses the required survey wording rather than an informal paraphrase.
EXAMPLES:
PASS:
1. "There will be a short survey after this call, please stay on the line and share your feedback."
2. "Call ke baad ek chhota sa survey aayega, kripya apna feedback zaroor dijiyega."
FAIL:
1. "Rate me good na." (informal, not the prescribed script)
2. (agent ends the call without pitching the survey when it was due)
""",

"Offering assistance": """METRIC_NAME: Offering Assistance
SPEAKER: Agent
ACTION: Offer help and invite the customer to share their query.
PASS_LOGIC: ANY
PASS_CRITERIA:
1. The agent asks how they can help or invites the customer to state their concern.
2. The agent proactively offers further assistance during the interaction.
EXAMPLES:
PASS:
1. "How may I assist you today?"
2. "Bataiye, main aapki kaise sahayata kar sakta hoon?"
FAIL:
1. "What do you want?" (no offer of assistance)
2. (agent provides no statement inviting or offering help)
""",

"Professional and Friendly Language with Pleasantries": """METRIC_NAME: Professional Friendly Pleasantries
SPEAKER: Agent
ACTION: Use professional and friendly language with pleasantries and without interrupting the customer.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent uses warm, courteous expressions (e.g. "please", "thank you", "sure", "my pleasure").
2. The agent does not cut off or talk over the customer mid-sentence.
EXAMPLES:
PASS:
1. "Sure, I'd be happy to help with that, thank you for your patience."
2. "Bilkul, mujhe aapki madad karke khushi hogi, dhanyavad."
FAIL:
1. "Ek minute, sunn lijiye." (interrupting the customer)
2. "Just tell me the number." (curt, no pleasantries)
""",

"Pronoun Errors": """METRIC_NAME: Pronoun Errors
SPEAKER: Agent
ACTION: Evaluate whether the agent uses pronouns that correctly match their referents in English speech.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. Pronouns agree in number and gender with the noun they refer to.
2. Subject and object pronouns are used in the grammatically correct position.
EXAMPLES:
PASS:
1. "Your card is ready; I will activate it for you now."
2. "The details are correct, so I have updated them."
FAIL:
1. "Your card is ready; I will activate them now." (should be "it")
2. "Me will help you with this." (should be "I")
""",

"Run-on or Incomplete Sentences": """METRIC_NAME: Run On Incomplete Sentences
SPEAKER: Agent
ACTION: Evaluate whether the agent speaks in complete, well-formed sentences rather than run-on or fragmented ones.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent's English statements form complete sentences with a subject and verb.
2. The agent avoids monosyllabic fragments and run-on sentences that join multiple ideas without structure.
EXAMPLES:
PASS:
1. "I have checked your account and the request is now complete."
2. "I will update your details and confirm before we end the call."
FAIL:
1. "Done." used as the entire English reply to a full question.
2. "So I checked and then it shows and you have to and then it will so yeah." (run-on)
""",

"Subject–Verb Agreement Errors": """METRIC_NAME: Subject Verb Agreement
SPEAKER: Agent
ACTION: Evaluate whether the agent's verbs agree in number with their subjects in English speech.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. Singular subjects take singular verb forms and plural subjects take plural verb forms.
2. Auxiliary and main verbs are conjugated correctly for the subject.
EXAMPLES:
PASS:
1. "Your details are updated and the request is complete."
2. "The customer has two cards linked to this number."
FAIL:
1. "Your details is updated." (should be "are")
2. "The amount are credited to your account." (should be "is")
""",

"Tense Errors": """METRIC_NAME: Tense Errors
SPEAKER: Agent
ACTION: Evaluate whether the agent uses the correct verb tense for the situation being described.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. Present, past, and future actions are expressed in the matching tense.
2. Verb tense remains consistent within each statement.
EXAMPLES:
PASS:
1. "I can see that the NEFT is being processed right now."
2. "I have updated your record and you will receive a confirmation."
FAIL:
1. "I am see NEFT kar rahe honge." (incorrect verb form for the present)
2. "Yesterday I will check your account." (future tense used for a past action)
""",

"Use of Power words": """METRIC_NAME: Use Of Power Words
SPEAKER: Agent
ACTION: Use positive power words that reassure and energise the customer.
PASS_LOGIC: ANY
PASS_CRITERIA:
1. The agent uses at least one positive power word such as "absolutely", "definitely", "certainly", "bilkul", or "zaroor".
2. The power word is used in a reassuring statement to the customer.
EXAMPLES:
PASS:
1. "Absolutely, I will definitely get this resolved for you."
2. "Bilkul, main zaroor aapki madad karunga."
FAIL:
1. "Okay, maybe I can try." (no power word, weak commitment)
2. (agent uses only neutral filler words with no reassuring power word)
""",

"Values customer & business": """METRIC_NAME: Values Customer And Business
SPEAKER: Agent
ACTION: Express appreciation that recognises the customer's value to the business.
PASS_LOGIC: ANY
PASS_CRITERIA:
1. The agent thanks the customer for being a valued or loyal customer of the bank.
2. The agent appreciates the customer's association, time, or relationship with the business.
EXAMPLES:
PASS:
1. "Thank you for being a valued customer of Axis Bank."
2. "Aap hamare valuable customer hain, aapka dhanyavad."
FAIL:
1. "Okay, next." (no appreciation expressed)
2. (agent never acknowledges the customer's value or relationship)
""",

"Verbal Nods": """METRIC_NAME: Verbal Nods
SPEAKER: Agent
ACTION: Use verbal nods to show active listening while the customer is speaking.
PASS_LOGIC: ANY
PASS_CRITERIA:
1. The agent uses brief acknowledgement cues such as "okay", "I see", "ji", "hmm", or "sure" while the customer explains.
2. The cues occur in response to the customer's statements rather than only at the end.
EXAMPLES:
PASS:
1. "Okay ... I see ... sure, please continue."
2. "Ji ... haan ... theek hai, bataiye."
FAIL:
1. (agent stays completely silent while the customer explains the full query)
2. "Number bataiye." (responds only with a demand, no listening cues)
""",

"Welcome Message": """METRIC_NAME: Welcome Message
SPEAKER: Agent
ACTION: Open the call with the prescribed welcome greeting elements.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent greets the customer and names the brand (e.g. "Welcome to Axis Bank").
2. The agent introduces themselves by name and offers assistance.
EXAMPLES:
PASS:
1. "Good afternoon, welcome to Axis Bank, my name is Ujjwal, how may I assist you?"
2. "Namaskar, Axis Bank mein aapka swagat hai, mera naam Sharad hai, bataiye kaise madad karun?"
FAIL:
1. "Hello, what do you want?"
2. "Yes, tell me." (no greeting, brand name, or self-introduction)
""",

"Wrong Prepositions": """METRIC_NAME: Wrong Prepositions
SPEAKER: Agent
ACTION: Evaluate whether the agent uses the correct prepositions in English phrases.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. Prepositions match standard English usage (e.g. "reply to", "inform about", "message regarding").
2. No preposition is substituted with an incorrect one.
EXAMPLES:
PASS:
1. "Please reply to this email and I will inform you about the status."
2. "I have sent a message regarding your request."
FAIL:
1. "Please reply on this email." (should be "to")
2. "I will inform you regarding this." (should be "about")
""",

"Wrong Question Formation": """METRIC_NAME: Wrong Question Formation
SPEAKER: Agent
ACTION: Evaluate whether the agent forms grammatically correct and courteous questions.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. Questions use correct word order and auxiliary verbs.
2. Permission questions use courteous forms (e.g. "may I" rather than "can I") where appropriate.
EXAMPLES:
PASS:
1. "May I have the last four digits of your card?"
2. "Could you please confirm your registered mobile number?"
FAIL:
1. "Can I take your card number?" (should use "may I" for permission)
2. "What issue you are facing?" (incorrect question word order)
""",

"Wrong Word Forms": """METRIC_NAME: Wrong Word Forms
SPEAKER: Agent
ACTION: Evaluate whether the agent uses the correct word form for the intended meaning in English speech.
PASS_LOGIC: ALL
PASS_CRITERIA:
1. The agent selects the correct word (noun, verb, adjective, or adverb) for the context.
2. The agent does not substitute a word with an incorrect or unintended one.
EXAMPLES:
PASS:
1. "Let me check your account and confirm the details."
2. "I am really very sorry for the inconvenience."
FAIL:
1. "Let me take your account." (should be "check")
2. "Really very sorry." (missing "I am", wrong sentence form)
""",
}


def main():
    out_path = "Axis input descriptions.tsv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["parameter_name", "parameter_description"])
        for name, desc in DESCRIPTIONS.items():
            w.writerow([name, desc.strip()])
    print(f"Wrote {out_path} with {len(DESCRIPTIONS)} parameters")


if __name__ == "__main__":
    main()
