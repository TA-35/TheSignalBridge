# Stanford gold drafts: pre-screen for the hand check

60 drafts; 18 have a proposed fix (listed first, with the reason), and 25 have at least one automatic flag. The flags only say where to look: check all 60 against the spot-check list in docs/COMPOSE_STYLE_GUIDE.md.

**To finish the check:** read all 60 drafts. In `data/gold_drafts/stanford_gold_fixes.json` set each proposal's "status" to "accept" or "reject" (edit its text first if you like), fix anything else by hand in the drafts file, then run `python Src/source/data_prep/gold_fixes.py stanford --checked-by <your name>`.

How much each flag means: **"kept as written, but the message is flagged"**, **NLI contradiction**, **dropped/added entity**, **hedge phrase left in** and **invented deadline** are the strongest. **"clear by the flag rule, but rewritten"** is often fine: the classifiers behind the flag rule are weak hints. **"politeness fell to low"** fires on many short, plain messages; only act on it if the rewrite really reads curt.

## 1. stanford_00001 (flagged: politeness=low)

**Automatic flags:**

- NLI reads the rewrite as contradicting the message

**Proposed fix:** NLI flags a contradiction: the draft changes "I wasn't sure" to "I'm not sure" and adds "anything I send", which the sender didn't say.

- rewrite -> I wasn't sure whether you were actually reading anything, because facts don't seem to affect you at all. And you accuse me of making things up?

**Message:** I wasn't sure whether you were actually reading anything because facts seem to bounce off of you like bullets off of Superman. And you accuse me of fantasies?

**Draft rewrite:** I'm not sure you're actually reading anything I send, because facts don't seem to affect you at all. And you accuse me of making things up?

**Notes:** Replaced the Superman simile with its plain meaning: facts don't affect you. / Kept the accusation and the closing question; only the wording changed.

**Meaning:** ask: ''; deadline: ''; urgency: medium; tone: 'angry, sarcastic, accusatory'; implied: 'The sender feels unheard, believes the other person ignores facts, and thinks that person is being hypocritical.'

## 2. stanford_00043 (flagged: politeness=high, circa=indirect)

**Automatic flags:**

- kept as written, but the message is flagged (politeness=high, circa=indirect)

**Proposed fix:** meaning.ask turns "Have you tried the script debugger in IE8?" into an instruction to try it.

- meaning -> {'ask': 'Say which debugger you are using, and whether you have tried the script debugger in IE8'}

**Message:** Which debugger are you using? Have you tried the script debugger in IE8?

**Draft rewrite:** Which debugger are you using? Have you tried the script debugger in IE8?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Say which debugger you are using; try the script debugger in IE8'; deadline: ''; urgency: low; tone: 'neutral, helpful'; implied: 'The sender suspects the script debugger in IE8 may help.'

## 3. stanford_00049 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Proposed fix:** "Wait ... before adding it" is wrong (the reference was already added), and dropping "Great" guesses it was sarcastic.

- rewrite -> Great. I understand why you added the reference, but I think it would be better to wait until it has been peer-reviewed.
- notes -> Replaced the rhetorical question with a plain suggestion: wait for peer review. / Kept 'Great' and your reasoning as written.
- meaning -> {'ask': 'Wait until the reference has been peer-reviewed', 'implied': 'The sender would rather the reference waited for peer review.'}

**Message:** Great. I understand why you added the ref, but it wouldn't hurt to just wait until it has been peer-reviewed, would it?

**Draft rewrite:** I understand why you added the reference. Could we wait until it has been peer-reviewed before adding it?

**Notes:** Replaced the rhetorical question with a direct request: wait for peer review. / "Great" read as sarcastic, so I left it out. Add it back if you meant it.

**Meaning:** ask: 'Wait until the reference has been peer-reviewed before adding it'; deadline: ''; urgency: low; tone: 'sarcastic, pointed, mild disagreement'; implied: 'The sender disagrees with adding the reference now and wants it held back; "Great" is likely sarcastic.'

## 4. stanford_00050 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Proposed fix:** Already clear: the draft adds "Let me know." and its note claims a split that didn't happen.

- rewrite -> Aha, problem solved, while I was writing that, you set up a new article! Should we change [URL] into a disambiguation page?
- notes -> Already clear, kept as written.

**Message:** Aha, problem solved, while I was writing that, you set up a new article! Should we change [URL] into a disambiguation page?

**Draft rewrite:** Aha, problem solved — while I was writing that, you set up a new article! Should we change [URL] into a disambiguation page? Let me know.

**Notes:** Split the run-on sentence so the question stands on its own. / Added 'Let me know' to show a reply is needed. / Kept [URL] and your casual tone as written.

**Meaning:** ask: 'Say whether we should change [URL] into a disambiguation page'; deadline: ''; urgency: low; tone: 'casual, pleased, upbeat'; implied: 'The sender is glad the problem is solved and wants an answer to the question.'

## 5. stanford_00055 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Proposed fix:** Judgment call: the bare "ANI?" is left for the reader to decode; it asks whether to take this to ANI.

- rewrite -> What's the best way to raise this? I can't remove it from him because I'm involved. Should I take it to ANI?
- notes -> Replaced 'take this up' with 'raise this'. / Turned 'ANI?' into a full question: should I take it to ANI? / Say what 'it' refers to, so the reader knows what is being raised.
- meaning -> {'ask': 'Advise on the best way to raise this, and whether to take it to ANI'}

**Message:** What's the best way to take this up? I can't remove it from him as I'm involved, ANI?

**Draft rewrite:** What's the best way to raise this? I can't remove it from him because I'm involved. ANI?

**Notes:** Replaced 'take this up' with 'raise this'. / Say what 'it' refers to, so the reader knows what is being raised. / Say who or what 'ANI' means; it isn't clear as written.

**Meaning:** ask: 'Advice on how to raise this'; deadline: ''; urgency: medium; tone: 'casual, unsure'; implied: "The sender can't handle this themselves because they are involved, so someone else may need to."

## 6. stanford_00056 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Proposed fix:** The second note explains HTML comments instead of describing a change; the change made (question moved first) isn't noted.

- notes -> Put your question first so it is easy to find. / You didn't say what "it" is. Name it so the reader knows what should be visible.

**Message:** Well... actually it is <!--commented-->. Could it be visible?

**Draft rewrite:** Could it be visible? Actually, it is <!--commented-->.

**Notes:** You didn't say what "it" is. Name it so the reader knows what should be visible. / Text inside <!-- --> is hidden when rendered, so the reader cannot see it.

**Meaning:** ask: 'Say whether it can be made visible'; deadline: ''; urgency: low; tone: 'hesitant, unclear'; implied: 'The sender suspects something is hidden or not showing.'

## 7. stanford_00060 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Proposed fix:** The draft turns the second question into a statement, while its note says both questions were kept.

- rewrite -> Does any content need to be restored? As far as I can see, the only edit I deleted was the redirect. Is that right?
- notes -> Replaced "rescuing" with "restored" so the meaning is literal. / Made your second question explicit: was the redirect the only edit deleted?

**Message:** Is there any content that needs rescuing? The only edit I seem to have deleted was the redirect?

**Draft rewrite:** Does any content need to be restored? The only edit I seem to have deleted was the redirect.

**Notes:** Replaced "rescuing" with "restored" so the meaning is literal. / Both questions need an answer; kept them as the main point.

**Meaning:** ask: 'Say whether any content needs to be restored, and confirm whether the redirect was the only edit deleted'; deadline: ''; urgency: medium; tone: 'neutral, checking, slightly worried'; implied: 'The sender deleted something and is unsure whether they removed more than the redirect.'

## 8. stanford_00005 (flagged: politeness=low)

**Proposed fix:** Urgency is high, but nothing in the message is time-critical; the other accusatory messages are medium.

- meaning -> {'urgency': 'medium'}

**Message:** Excuse me? What are you accusing me of doing?

**Draft rewrite:** What are you accusing me of doing? I'm upset by this.

**Notes:** Named the upset behind 'Excuse me?' so the tone isn't misread. / Kept the question as the ask: say what the accusation is.

**Meaning:** ask: 'Tell me what you are accusing me of doing'; deadline: ''; urgency: high; tone: 'offended, defensive'; implied: 'The sender feels accused and is upset by it.'

## 9. stanford_00007 (flagged: politeness=low)

**Proposed fix:** "seriously" was dropped, weakening the insistence the note says was kept; the note also claims a split that didn't happen.

- rewrite -> PS — I would seriously like an answer to my question above. What is your native language, and where do you come from?
- notes -> Kept your insistence on getting an answer. / 'My question above' points to an earlier message. Check the reader can still see it.

**Message:** PS, I would seriously like an answer to my question above. What is your native language and where do you come from?

**Draft rewrite:** PS — I would like an answer to my question above. What is your native language, and where do you come from?

**Notes:** Split into two short sentences; kept the insistence. / 'My question above' points to an earlier message. Check the reader can still see it.

**Meaning:** ask: 'Answer the question about their native language and where they come from'; deadline: ''; urgency: medium; tone: 'insistent, direct'; implied: 'The sender feels the earlier question was not answered.'

## 10. stanford_00009 (flagged: politeness=low)

**Proposed fix:** The second note says the sentence was split; the draft only changed "BUT" to "but".

- notes -> Fixed the typo "don~t" to "don't". / Changed the capitalised "BUT" to "but"; the question is unchanged.

**Message:** Brenda, I still don~t understand. Are you saying Antonio Rumeu de Armas is a primary source BUT Rachael Bright Hicks is not a primary source?

**Draft rewrite:** Brenda, I still don't understand. Are you saying Antonio Rumeu de Armas is a primary source, but Rachael Bright Hicks is not a primary source?

**Notes:** Fixed the typo "don~t" to "don't". / Split into two sentences so the question is easier to read.

**Meaning:** ask: 'Confirm whether Antonio Rumeu de Armas is a primary source and Rachael Bright Hicks is not'; deadline: ''; urgency: medium; tone: 'confused, direct'; implied: 'Frustration at having to ask again; the sender wants a clear yes or no.'

## 11. stanford_00015 (flagged: hedge, politeness=high)

**Proposed fix:** The draft adds "Hi", which the sender didn't write.

- rewrite -> Leah, thanks a lot for your help with the article. Why was the link to the article for "Advent of Divine Justice" deleted?

**Message:** Leah, thanks a lot for your help with the article. But I'm just curious - why was the link to the article for "Advent of Divine Justice" deleted?

**Draft rewrite:** Hi Leah, thanks a lot for your help with the article. Why was the link to the article for "Advent of Divine Justice" deleted?

**Notes:** Dropped "I'm just curious" so the question reads as a direct ask. / Kept your thanks and the article title exactly as written. / You don't say if you want the link restored. Add that if you do.

**Meaning:** ask: 'Explain why the link to the article for "Advent of Divine Justice" was deleted'; deadline: ''; urgency: low; tone: 'polite, curious, slightly concerned'; implied: 'The sender noticed the deletion and may want the link restored, but does not say so.'

## 12. stanford_00020 (flagged: politeness=low)

**Proposed fix:** Optional: "Please explain why you reverted ... without any explanation" reads oddly and turns a direct question into a demand.

- rewrite -> Why did you revert my edits to those articles without any explanation?
- notes -> Dropped "What's going on?" — it was vague and the real ask follows. / Kept your question as the ask: why the edits were reverted.

**Message:** What's going on? Why did you revert my edits to those articles without any explanation?

**Draft rewrite:** Please explain why you reverted my edits to those articles without any explanation.

**Notes:** Made the ask direct: explain why the edits were reverted. / Dropped "What's going on?" — it was vague and the real ask follows.

**Meaning:** ask: "Explain why the sender's edits to the articles were reverted"; deadline: ''; urgency: medium; tone: 'frustrated, direct'; implied: 'The sender is upset that the edits were reverted with no explanation.'

## 13. stanford_00022 (flagged: politeness=high)

**Proposed fix:** The draft adds "Hi,", which the sender didn't write.

- rewrite -> Would you like all of the data? I tried to use logcat, but there's so much data that I don't know how to sort through it.

**Message:** I tried to use logcat, but there's so much data provided I don't know how to sort through it. would you like all of the data?

**Draft rewrite:** Hi, would you like all of the data? I tried to use logcat, but there's so much data that I don't know how to sort through it.

**Notes:** Led with your question so it's easy to answer. / You didn't ask for help sorting the data. Add that if you want it.

**Meaning:** ask: 'Answer whether the sender should send all of the logcat data'; deadline: ''; urgency: low; tone: 'neutral, a bit stuck'; implied: 'The sender is overwhelmed by the logcat data and may want help narrowing it down.'

## 14. stanford_00023 (flagged: politeness=high, circa=indirect)

**Proposed fix:** "On the small side" means a bit small; "too small" is stronger than the sender said.

- rewrite -> Hi. The font size for the links in this template may be a bit small. It seems to be floating okay. Do I need to check more places where this template is used?
- meaning -> {'implied': 'The sender thinks the link font size may be a bit small and wants a decision from the reader.'}

**Message:** Hi. The font-size for the links in this template may be on the small side, but it seems to be floating okay -- or do I need to check more places where it's used?

**Draft rewrite:** Hi. The font size for the links in this template may be too small. It seems to be floating okay. Do I need to check more places where this template is used?

**Notes:** 'Floating okay' is vague. Say what looks fine, such as the layout. / Made 'it' explicit as the template, so the question is clear. / Kept the question as the ask; a reply is needed.

**Meaning:** ask: 'Say whether the sender needs to check more places where this template is used'; deadline: ''; urgency: low; tone: 'tentative, polite, unsure'; implied: 'The sender suspects the link font size is too small and wants a decision from the reader.'

## 15. stanford_00030 (flagged: politeness=high)

**Proposed fix:** The second note says a long sentence was split; the draft has the same two sentences as the message.

- notes -> 'The more powerful topic' is vague. Name it so the reader knows what to expand on.

**Message:** Alexis Ferguson: At my current stage of design, it is more of a logic based game rather than an animation driven game. Out of curiosity, could you expand on the more powerful topic you were mentioning?

**Draft rewrite:** Alexis Ferguson: At my current stage of design, this is more of a logic-based game than an animation-driven game. Out of curiosity, could you expand on the more powerful topic you mentioned?

**Notes:** 'The more powerful topic' is vague. Name it so the reader knows what to expand on. / Split one long sentence into two so each idea stands alone.

**Meaning:** ask: 'Expand on the more powerful topic they mentioned'; deadline: ''; urgency: low; tone: 'polite, curious, professional'; implied: 'The sender wants more detail about that topic.'

## 16. stanford_00035 (flagged: politeness=low)

**Proposed fix:** "Would you please stop?" became "Please stop." - curter than the sender, and no note says so.

- rewrite -> So far, four editors on [URL] have told you about your edit-warring. Would you please stop?

**Message:** So far there are four editors on [URL] who have called you on your edit-warring. Would you please stop?

**Draft rewrite:** So far, four editors on [URL] have told you about your edit-warring. Please stop.

**Notes:** Replaced 'called you on' with the literal 'told you about'. / Kept the count of four and [URL] exactly as written.

**Meaning:** ask: 'Stop edit-warring'; deadline: ''; urgency: medium; tone: 'frustrated, direct'; implied: 'Other editors have already raised this; the sender is losing patience.'

## 17. stanford_00040 (flagged: politeness=low, circa=indirect)

**Proposed fix:** The first note says the question was moved first; nothing was moved.

- notes -> Made each question a full sentence so the ask is easy to answer. / Kept your guess as a question, so it reads as a check, not a fact.

**Message:** That's not clear, what kind of distance? You mean orthogonal distance from a side of original rectangle to another one?

**Draft rewrite:** This isn't clear to me. What kind of distance do you mean? Do you mean the orthogonal distance from one side of the original rectangle to another one?

**Notes:** Put the question first so the ask is easy to answer. / Kept your guess as a question, so it reads as a check, not a fact.

**Meaning:** ask: 'Explain what kind of distance is meant'; deadline: ''; urgency: medium; tone: 'direct, confused'; implied: 'The sender found the earlier explanation unclear.'

## 18. stanford_00041 (flagged: circa=indirect)

**Proposed fix:** The first note says the question was moved first; it already was.

- notes -> Made the first question a full request: can you explain what you mean? / Kept the quoted sentence exactly as written.

**Message:** What do you mean by this, "I'm actually testing the solution to check, if it is not adapted to single specific format of token only." What is single specific format?

**Draft rewrite:** Can you explain what you mean by this: "I'm actually testing the solution to check, if it is not adapted to single specific format of token only."? What is a single specific format?

**Notes:** Put the question first so the ask is easy to find. / Kept the quoted sentence exactly as written.

**Meaning:** ask: 'Explain what "single specific format of token only" means'; deadline: ''; urgency: medium; tone: 'confused, direct'; implied: 'The sender did not understand the quoted sentence and wants it clarified.'

## 19. stanford_00024 (flagged: circa=indirect)

**Automatic flags:**

- dropped ["woun't understand"]
- politeness fell medium -> low (reads blunt?)

**Message:** I can, but it is written in Lithuanian language, so I think you woun't understand. Anyway, where should I put it?

**Draft rewrite:** I can. But it is written in Lithuanian, so I think you won't understand it. Where should I put it?

**Notes:** Name what 'it' is, so the reader knows what you're talking about. / Fixed the typo 'woun't' to 'won't'. / Kept your doubt about the language as written.

**Meaning:** ask: 'Say where to put it'; deadline: ''; urgency: low; tone: 'casual, a little blunt'; implied: 'The sender doubts the reader will understand the Lithuanian text.'

## 20. stanford_00058 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)
- politeness fell medium -> low (reads blunt?)

**Message:** Assuming I don't have a masterlink, I assume I'd need to use a chain tool. (One of my multitools has one, I think.) Does pushing a pin out weaken the chain, or am I worried over nothing?

**Draft rewrite:** Two questions:
- Without a masterlink, do I need to use a chain tool? I think one of my multitools has one.
- Does pushing a pin out weaken the chain, or am I worried over nothing?

**Notes:** Put both questions first as a list so each gets an answer. / Kept your uncertainty ('I think') instead of stating it as fact.

**Meaning:** ask: 'Confirm whether a chain tool is needed without a masterlink, and whether pushing a pin out weakens the chain'; deadline: ''; urgency: low; tone: 'casual, thinking aloud, unsure'; implied: 'The sender believes they need a chain tool and is unsure whether that damages the chain.'

## 21. stanford_00002 (flagged: politeness=low, circa=indirect)

**Automatic flags:**

- kept as written, but the message is flagged (politeness=low, circa=indirect)

**Message:** If you're talking about the Recycling Troll, I've never blocked him. Why do you think I have?

**Draft rewrite:** If you're talking about the Recycling Troll, I've never blocked him. Why do you think I have?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Explain why you think I blocked him'; deadline: ''; urgency: medium; tone: 'defensive, casual'; implied: 'The sender feels accused of blocking him and is pushing back.'

## 22. stanford_00003 (flagged: politeness=high, circa=indirect)

**Automatic flags:**

- kept as written, but the message is flagged (politeness=high, circa=indirect)

**Message:** Could you be a bit more specific? What do you mean by short key for scroll?

**Draft rewrite:** Could you be a bit more specific? What do you mean by short key for scroll?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Explain what "short key for scroll" means, in more specific terms'; deadline: ''; urgency: medium; tone: 'polite, asking for clarification'; implied: ''

## 23. stanford_00019 (flagged: circa=indirect)

**Automatic flags:**

- kept as written, but the message is flagged (circa=indirect)

**Message:** What's your platform? FPGA or microcontroller?

**Draft rewrite:** What's your platform? FPGA or microcontroller?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Tell me which platform you use: FPGA or microcontroller'; deadline: ''; urgency: low; tone: 'casual, direct'; implied: ''

## 24. stanford_00026 (flagged: circa=indirect)

**Automatic flags:**

- added ['5-second']

**Message:** Do you want it to automatically be called with a delay of 5 seconds between invocations, or will this be called in response to a user action and you want to ensure that it waits at least 5 seconds after the last invocation before going again? If the latter, should the user be able to queue up events, or should the input be ignored if 5 seconds have not elapsed?

**Draft rewrite:** I need to know how the 5-second delay should work. Which of these do you want?
- It is called automatically, with a delay of 5 seconds between invocations.
- It is called in response to a user action, and it waits at least 5 seconds after the last invocation before going again.

If you want the second option, should the user be able to queue up events, or should the input be ignored if 5 seconds have not elapsed?

**Notes:** Split the two options into bullets so they can be compared at a glance. / Kept the follow-up question about queuing events or ignoring input.

**Meaning:** ask: 'Choose how the 5-second delay should work, and answer the follow-up about queuing or ignoring input'; deadline: ''; urgency: low; tone: 'neutral, technical, seeking clarification'; implied: 'The sender needs a decision before building this.'

## 25. stanford_00028 (flagged: politeness=high)

**Automatic flags:**

- dropped ['2014']

**Message:** Thanks for the username change. Now, one last thingu2014since the account 'Dalahxe4st' already exists on Swedish Wikipedia and doesn't appear to have been taken over automatically, where should I go to take care of that?

**Draft rewrite:** Thanks for the username change. One last thing: where should I go to take care of the account 'Dalahxe4st'? It already exists on Swedish Wikipedia, and it doesn't appear to have been taken over automatically.

**Notes:** Moved your question to the front so the ask is easy to find. / Kept 'Dalahxe4st' and Swedish Wikipedia exactly as written. / Fixed the broken dash character (u2014) into a normal dash.

**Meaning:** ask: "Say where to go to take care of the account 'Dalahxe4st' on Swedish Wikipedia"; deadline: ''; urgency: low; tone: 'polite, appreciative, matter-of-fact'; implied: "This is the sender's last outstanding item and they want it resolved too."

## 26. stanford_00029 (flagged: politeness=high)

**Automatic flags:**

- kept as written, but the message is flagged (politeness=high)

**Message:** What are the project settings for the version you are debugging? For example, is the Debugging element defined so that there is a corresponding pdb file?

**Draft rewrite:** What are the project settings for the version you are debugging? For example, is the Debugging element defined so that there is a corresponding pdb file?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Tell me the project settings for the version you are debugging, including whether the Debugging element is defined so there is a corresponding pdb file'; deadline: ''; urgency: medium; tone: 'neutral, precise'; implied: ''

## 27. stanford_00031 (flagged: politeness=low, circa=indirect)

**Automatic flags:**

- kept as written, but the message is flagged (politeness=low, circa=indirect)

**Message:** It looks like the string is double encoded: first Html Encoded and then URL encoded. Why is that so?

**Draft rewrite:** It looks like the string is double encoded: first Html Encoded and then URL encoded. Why is that so?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Explain why the string is double encoded (HTML encoded, then URL encoded)'; deadline: ''; urgency: low; tone: 'neutral, questioning'; implied: 'The sender thinks the double encoding is wrong and wants a reason for it.'

## 28. stanford_00038 (flagged: politeness=high)

**Automatic flags:**

- kept as written, but the message is flagged (politeness=high)

**Message:** Hey. I'm proposing a [URL] - would you be interested in coming along?

**Draft rewrite:** Hey. I'm proposing a [URL] - would you be interested in coming along?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Reply whether you are interested in coming along'; deadline: ''; urgency: low; tone: 'casual, friendly'; implied: ''

## 29. stanford_00046 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** Note them where? On their talk page, or by adding them to the list you created at ArbCom so a clerk can notify them?

**Draft rewrite:** Where should I note them? Two options:
- on their talk page
- by adding them to the list you created at ArbCom, so a clerk can notify them

**Notes:** Split the two options into a list so they are easy to compare. / "Them" is not named. Say what it refers to so the reader does not guess.

**Meaning:** ask: 'Tell me where to note them'; deadline: ''; urgency: low; tone: 'neutral, asking for clarification'; implied: 'The sender is offering two options and wants the reader to pick one.'

## 30. stanford_00047 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** by "without a public facing server" do you mean the kml has to be on the local machine, or that you don't want to have to bother with installing/configuring/buying a public website? And, does the custom map you want to make need to be seen by others or just you?

**Draft rewrite:** Two questions:

- By "without a public facing server", do you mean the kml has to be on the local machine, or that you don't want to install, configure or buy a public website?
- Does the custom map you want to make need to be seen by others, or just by you?

**Notes:** Split the two questions into bullets so neither gets missed. / Kept both options in the first question, since it is an either/or.

**Meaning:** ask: 'Answer two questions: what "without a public facing server" means, and who needs to see the custom map'; deadline: ''; urgency: medium; tone: 'neutral, clarifying'; implied: 'The sender needs these answers before they can proceed.'

## 31. stanford_00048 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** In what way does the daemon act differently in those two scenarios? Form the perspective of your daemon, how is a shutdown + startup different than a reboot?

**Draft rewrite:** How does the daemon act differently in those two scenarios? From the daemon's perspective, how is a shutdown and startup different from a reboot?

**Notes:** Fixed the typo 'Form' to 'From'. / Kept both questions and their meaning as written.

**Meaning:** ask: "Explain how the daemon acts differently in the two scenarios, and from the daemon's perspective how a shutdown and startup differs from a reboot"; deadline: ''; urgency: medium; tone: 'neutral, technical'; implied: ''

## 32. stanford_00051 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** Well, yes, obviously (but I sort of assumed that the same exemptions would apply to 1RR as 3RR - is that not the case?) Should I self-rv?

**Draft rewrite:** Yes. I assumed the same exemptions apply to 1RR as to 3RR. Is that not the case? Should I self-rv?

**Notes:** Dropped 'obviously' so the yes doesn't read as sarcastic. / Kept 1RR, 3RR and self-rv exactly as you wrote them.

**Meaning:** ask: 'Confirm whether the same exemptions apply to 1RR as to 3RR, and say whether I should self-rv'; deadline: ''; urgency: medium; tone: 'casual, dry, slightly sarcastic'; implied: 'The sender thinks the answer was obvious and is unsure why it was asked.'

## 33. stanford_00052 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** Again: What attributes do you have? What is the structure of your data?

**Draft rewrite:** I'm asking again:
- What attributes do you have?
- What is the structure of your data?

**Notes:** Split the two questions into bullets so both get answered. / 'Again' shows you asked before; kept it so the repeat is clear.

**Meaning:** ask: 'Tell me what attributes you have and the structure of your data'; deadline: ''; urgency: medium; tone: 'neutral, slightly impatient'; implied: 'This has been asked before and not yet answered.'

## 34. stanford_00053 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** Are you really sure all the code the expression is running is built for Debug? There is no dependency that might be release built by chance?

**Draft rewrite:** Could you confirm two things:
- that all the code the expression is running is built for Debug
- that no dependency is release-built by chance

I want to be sure, so please check both.

**Notes:** Split the two questions into bullets so both get answered. / Kept the doubt behind 'really sure' as a plain request to confirm.

**Meaning:** ask: 'Confirm that all the code the expression is running is built for Debug, and that no dependency is release-built by chance'; deadline: ''; urgency: medium; tone: 'skeptical, double-checking'; implied: 'The sender suspects a dependency may be release-built.'

## 35. stanford_00054 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** "I'm fairly new to java programming (or programming in general)" So, have you used another programming language before? Which one?

**Draft rewrite:** You said you're fairly new to Java programming (or programming in general). Could you tell me:
- Have you used another programming language before?
- If so, which one?

**Notes:** Split the two questions into bullets so both get answered. / Kept your quote of their words as context for the questions.

**Meaning:** ask: 'Say whether they have used another programming language before, and which one'; deadline: ''; urgency: low; tone: 'casual, curious'; implied: ''

## 36. stanford_00057 (clear)

**Automatic flags:**

- the message is clear by the flag rule, but it was rewritten (needless rewrite?)

**Message:** Herlihy & Shavit's book, The Art of Multiprocessor Programming, or "Lock-free linked lists and skip lists" or java.util.concurrent or Practical lock-freedom. Have you considered using a concurrent hash table like a hopscotch hash table?

**Draft rewrite:** Have you considered using a concurrent hash table like a hopscotch hash table?

- Herlihy & Shavit's book, The Art of Multiprocessor Programming
- "Lock-free linked lists and skip lists"
- java.util.concurrent
- Practical lock-freedom

**Notes:** Moved the question to the top so the ask is seen first. / The list is now bullets, one item per line. / Say what the list is for: reading, or alternatives to the hash table.

**Meaning:** ask: 'Consider using a concurrent hash table like a hopscotch hash table'; deadline: ''; urgency: low; tone: 'neutral, technical, terse'; implied: 'The listed items are offered as related reading or alternatives, but the input does not say which.'

## 37. stanford_00004 (flagged: politeness=low, circa=indirect)

**Message:** What's the purpose? Maybe [URL] is relevant?

**Draft rewrite:** What is the purpose? Maybe [URL] is relevant?

**Notes:** Name what you're asking about, so the reader knows what "the purpose" refers to. / Kept [URL] exactly as written.

**Meaning:** ask: 'Explain the purpose, and consider whether [URL] is relevant'; deadline: ''; urgency: low; tone: 'brief, questioning'; implied: "The sender doesn't see the point of whatever this is about."

## 38. stanford_00006 (flagged: politeness=low)

**Message:** Speaking of FPC closures, is it common practice to close the likes of the Emu feeding video or the White Ibis, which had nothing but weak supports and supports (not enough total votes, but that was all) as "Not Promoted"? Isn't that what the "Nominations 7 days or older - Decision Time" section is for?

**Draft rewrite:** Speaking of FPC closures, I have two questions:
- Is it common practice to close videos like the Emu feeding video or the White Ibis as "Not Promoted"? They had nothing but weak supports and supports, and not enough total votes, but that was all.
- Isn't that what the "Nominations 7 days or older - Decision Time" section is for?

**Notes:** Split the two questions into bullets so each one gets an answer. / "Weak supports and supports" reads oddly. Check that wording before sending.

**Meaning:** ask: 'Answer whether closing videos like the Emu feeding video or the White Ibis as "Not Promoted" is common practice, and whether that is what the "Nominations 7 days or older - Decision Time" section is for'; deadline: ''; urgency: low; tone: 'neutral, questioning, puzzled'; implied: 'The sender suspects these closures were not the right call.'

## 39. stanford_00008 (flagged: politeness=low)

**Message:** That machine only cooks the crepes on one side. Wouldn't they stick together in the 'Finished' tray?

**Draft rewrite:** That machine only cooks the crepes on one side. Would the crepes stick together in the 'Finished' tray? I think they would.

**Notes:** Made 'Wouldn't they' a direct question, then stated your expectation plainly. / No deadline or action was given, so none was added.

**Meaning:** ask: "Answer whether the crepes would stick together in the 'Finished' tray"; deadline: ''; urgency: low; tone: 'casual, questioning'; implied: 'The sender expects the crepes will stick together, and sees this as a problem with the machine.'

## 40. stanford_00010 (flagged: politeness=low)

**Message:** Never did it, but I'm curious! Isn't it too "starchy"?

**Draft rewrite:** I've never done it, but I'm curious. Isn't it too "starchy"?

**Notes:** "It" is unclear here. Name what you're asking about so the reader knows. / "Starchy" in quotes could mean stiff or literal. Say which you mean.

**Meaning:** ask: 'Answer whether it is too "starchy"'; deadline: ''; urgency: low; tone: 'casual, curious'; implied: "The sender has no experience with it and is asking for the reader's view."

## 41. stanford_00011 (flagged: politeness=high)

**Message:** Yes, the edges are always axis aligned (I will update the post). Could you give more detail on the scan line approach? Thx.

**Draft rewrite:** Yes, the edges are always axis aligned. I will update the post. Could you give more detail on the scan line approach? Thanks.

**Notes:** Moved the post update out of brackets so the commitment is easy to see. / Kept your ask and the confirmation in the same order.

**Meaning:** ask: 'Give more detail on the scan line approach'; deadline: ''; urgency: low; tone: 'casual, polite, direct'; implied: 'The sender confirms the edges are axis aligned and will update the post.'

## 42. stanford_00012 (flagged: politeness=high)

**Message:** I've had a go at sorting out markup for footnotes. Also many (most) of the external links were either direct-links or indirect-mentions of single research papers; I've worked these up where possible, but should they be moved from "External links" to "References" or better still to relevent place in the artice as footnotes?

**Draft rewrite:** Could you tell me where the external links should go? The options are:
- move them from "External links" to "References"
- move them into the relevant place in the article as footnotes, which I think would be better

Many (most) of the external links were either direct links or indirect mentions of single research papers. I've worked these up where possible. I've also had a go at sorting out the markup for footnotes.

**Notes:** Put your question first so the decision you need is easy to find. / Listed the two options as bullets so they can be compared. / Kept your preference for footnotes, since "better still" said so.

**Meaning:** ask: 'Decide whether the external links should be moved from "External links" to "References", or into the relevant place in the article as footnotes'; deadline: ''; urgency: low; tone: 'neutral, detailed, asking for guidance'; implied: 'The sender thinks footnotes would be better, and wants the reader to make the call.'

## 43. stanford_00013 (flagged: politeness=low)

**Message:** Also, both [URL] and [URL] wikilink "hiatus", which goes to a disambiguation page. What meaning of the word did you intend?

**Draft rewrite:** Also, what meaning of the word "hiatus" did you intend? Both [URL] and [URL] wikilink "hiatus", which goes to a disambiguation page.

**Notes:** Moved your question to the front so the ask is easy to find. / Kept both [URL] placeholders and the wording about the disambiguation page.

**Meaning:** ask: 'Say which meaning of the word "hiatus" you intended'; deadline: ''; urgency: low; tone: 'neutral, direct'; implied: ''

## 44. stanford_00014 (flagged: politeness=low)

**Message:** Don't stop editing. Maybe a request at [URL] would be of use?

**Draft rewrite:** Don't stop editing. It might be useful to make a request at [URL].

**Notes:** You didn't say what to edit. Add the document or file name. / Kept [URL] as written and left the request as a suggestion, not a task.

**Meaning:** ask: 'Keep editing, and consider making a request at [URL]'; deadline: ''; urgency: low; tone: 'casual, blunt'; implied: 'The request at [URL] is a suggestion, not a required task.'

## 45. stanford_00016 (flagged: politeness=high)

**Message:** I created this for you. However as a registered user, do you know you can create categories by yourself?

**Draft rewrite:** I created this for you. Did you know that, as a registered user, you can create categories yourself?

**Notes:** Made the question clear: did you know you can create categories yourself? / Dropped 'However', which didn't change the meaning.

**Meaning:** ask: 'Answer whether you knew you can create categories yourself'; deadline: ''; urgency: low; tone: 'neutral, helpful'; implied: 'The sender is pointing out a feature you may not know about.'

## 46. stanford_00017 (flagged: circa=indirect)

**Message:** More like an API to be used by a mobile device. Does it matter what kind of client uses the API?

**Draft rewrite:** It's more like an API to be used by a mobile device. Does it matter what kind of client uses the API?

**Notes:** The message doesn't say what 'it' refers to. Name it so the reader can follow. / Kept the question as written; it is already clear.

**Meaning:** ask: 'Say whether the kind of client using the API matters'; deadline: ''; urgency: low; tone: 'neutral, clarifying'; implied: 'The sender is correcting an earlier description and checking whether the client type is relevant.'

## 47. stanford_00018 (flagged: politeness=high)

**Message:** Thanks. As an aside, since this did turn out to be factual, just very hard to source, do you think the community would countenance an unblock request from Linda if he accepted some strict unblock conditions (such as packing in the 'systemic bias' thing, discussing his edits in a less confrontational manner etc)?

**Draft rewrite:** Thanks. As an aside: this did turn out to be factual, just very hard to source. Do you think the community would approve an unblock request from Linda if he accepted strict unblock conditions, such as:
- stopping the 'systemic bias' point
- discussing his edits in a less confrontational way

**Notes:** Replaced 'countenance' and 'packing in' with plain words. / Listed the two conditions so they are easy to answer. / You use 'Linda' and 'he' for the same person. Check that wording.

**Meaning:** ask: 'Say whether the community would approve an unblock request from Linda if he accepted strict unblock conditions'; deadline: ''; urgency: low; tone: 'polite, tentative, formal'; implied: "The sender thinks this is worth considering and wants the reader's opinion."

## 48. stanford_00021 (flagged: politeness=low)

**Message:** I hate that they give no choices for being anonymous. Why do I have to use my real full name to sign up?

**Draft rewrite:** I hate that there's no option to sign up anonymously. Why do I have to use my real full name to sign up?

**Notes:** Kept your frustration as written; only made 'no choices for being anonymous' plainer. / The question reads as venting. If you want an answer, ask the reader directly. / If you want this changed, add what you want instead.

**Meaning:** ask: ''; deadline: ''; urgency: low; tone: 'frustrated, venting'; implied: 'The sender dislikes being forced to use their real full name.'

## 49. stanford_00025 (flagged: politeness=low)

**Message:** wait... what? Since there's only one actual neutral connection coming into the box, that one has to somehow connect to all five lamps, doesn't it?

**Draft rewrite:** Wait, I'm confused. There's only one neutral connection coming into the box. Doesn't that one have to connect to all five lamps?

**Notes:** Made the question explicit and kept your uncertainty. / If the reader may not know which box, name it.

**Meaning:** ask: 'Confirm whether the single neutral connection must connect to all five lamps'; deadline: ''; urgency: low; tone: 'puzzled, casual'; implied: 'The sender thinks the answer is yes and wants it confirmed.'

## 50. stanford_00027 (flagged: politeness=low)

**Message:** He's already been blocked, as far as I can tell. Is there anything else that needs to be done, at this point?

**Draft rewrite:** He's already been blocked, as far as I can tell. Is there anything else that needs to be done?

**Notes:** Cut the filler "at this point"; the question is unchanged. / If the reader may not know who "he" is, add his name.

**Meaning:** ask: 'Say whether anything else needs to be done'; deadline: ''; urgency: low; tone: 'neutral, slightly uncertain'; implied: 'The sender is not fully certain the block is confirmed.'

## 51. stanford_00032 (flagged: politeness=low)

**Message:** Yes, I just saw that. DJ, if you wished to delete the still tagged pages then that was your judgement call but to delete pages which I had already declined a speedy on was rather bad form wouldn't you say?

**Draft rewrite:** Yes, I just saw that. DJ, deleting the still-tagged pages was your judgement call. But you also deleted pages where I had already declined a speedy deletion. I don't think that was acceptable. Do you agree?

**Notes:** Replaced "bad form" and "wouldn't you say?" with their literal meaning. / Kept your "yes" and the difference between the two kinds of deletion.

**Meaning:** ask: 'Agree that deleting the pages was out of line'; deadline: ''; urgency: medium; tone: 'annoyed, confrontational, sarcastic'; implied: 'The sender is angry that DJ deleted pages they had already declined a speedy deletion on, and thinks DJ overstepped.'

## 52. stanford_00033 (flagged: politeness=low)

**Message:** Rather than tell me how wrong I was to close certain afd's maybe your time would be better spent dealing with the current afd backlog [URL]. If my decisions were so wrong why haven't you re-opened them?

**Draft rewrite:** Please stop telling me I was wrong to close certain afd's. I'm frustrated by it, and I'd rather you spend that time on the current afd backlog [URL]. If my decisions were so wrong, why haven't you re-opened them?

**Notes:** Removed the sarcasm; the ask is now direct: deal with the afd backlog. / Named the frustration the sarcasm was carrying. / No deadline was given. Add one if this is urgent.

**Meaning:** ask: "Deal with the current afd backlog, and answer why the closed afd's haven't been re-opened"; deadline: ''; urgency: medium; tone: 'frustrated, sarcastic, confrontational'; implied: 'The sender feels unfairly criticised and wants the criticism to stop.'

## 53. stanford_00034 (flagged: circa=indirect)

**Message:** You are correct that the science is not copyright, but the purpose of the cite is [URL]. If I want to check your equation, where should I look?

**Draft rewrite:** You are correct that the science is not copyright. The purpose of the citation is [URL]. If I want to check your equation, where should I look?

**Notes:** Split the long sentence so each idea stands alone. / 'The purpose of the cite is [URL]' is unclear. Say what the citation is for.

**Meaning:** ask: "Say where the sender should look to check the reader's equation"; deadline: ''; urgency: low; tone: 'neutral, correcting, curious'; implied: 'The sender thinks the citation still matters, even though the science is not copyright.'

## 54. stanford_00036 (flagged: politeness=high)

**Message:** Please see [URL]. Can you help?

**Draft rewrite:** Please see [URL]. Can you help with this?

**Notes:** You didn't say what kind of help you need. Add it so the reader knows what to do. / Kept [URL] exactly as written.

**Meaning:** ask: 'Help with something at [URL]'; deadline: ''; urgency: medium; tone: 'neutral, polite'; implied: 'The sender wants the reader to look at the link and then help.'

## 55. stanford_00037 (flagged: politeness=low)

**Message:** Not to start a war, but I can see another side to that. Why develop (test, deploy, maintain) two solutions where one will do?

**Draft rewrite:** I don't want to start an argument, but I can see another side to that. Why develop two solutions (test, deploy, maintain) when one will do?

**Notes:** Replaced 'not to start a war' with what it means: I don't want to start an argument. / Kept the question as written; it is the ask.

**Meaning:** ask: 'Explain why two solutions are being developed when one will do'; deadline: ''; urgency: low; tone: 'cautious, direct, questioning'; implied: 'The sender disagrees with building two solutions and expects pushback.'

## 56. stanford_00039 (flagged: politeness=low, circa=indirect)

**Message:** What is your first try? Why don't you think it's optimal, or where have you gotten stuck?

**Draft rewrite:** Could you tell me:
- what your first attempt was
- why you think it isn't optimal, or where you got stuck

**Notes:** Split the questions into a list so each one is easy to answer. / Changed 'first try' to 'first attempt' for clarity.

**Meaning:** ask: "Explain your first attempt: why you think it isn't optimal, or where you got stuck"; deadline: ''; urgency: medium; tone: 'direct, probing'; implied: 'The sender expects the reader to have already tried something.'

## 57. stanford_00042 (flagged: politeness=low, circa=indirect)

**Message:** "Office actions will be clearly indicated both during and after to prevent ambiguities." -- [URL]. So then does that mean it was probably DMCA?

**Draft rewrite:** Does this mean it was probably DMCA? The source at [URL] says: "Office actions will be clearly indicated both during and after to prevent ambiguities."

**Notes:** Moved your question to the front so the ask is clear. / Say what "it" refers to so the reader knows what you mean.

**Meaning:** ask: 'Say whether it was probably DMCA'; deadline: ''; urgency: low; tone: 'neutral, inquiring'; implied: 'The sender suspects it was a DMCA action.'

## 58. stanford_00044 (flagged: politeness=low)

**Message:** At least there's nothing ungrammatical about them. Could you elaborate on why you have doubts about their correctness?

**Draft rewrite:** Could you explain why you have doubts about their correctness? The grammar is fine, at least.

**Notes:** Put your question first and made the grammar remark plain, not sarcastic. / 'Them' is vague. Name the items so the reader knows what you mean.

**Meaning:** ask: 'Explain why they have doubts about whether the items are correct'; deadline: ''; urgency: low; tone: 'defensive, sarcastic, direct'; implied: 'The sender feels their work is being questioned and is pushing back; they believe grammar is not the problem.'

## 59. stanford_00045 (flagged: politeness=high)

**Message:** I could go on from here, but this is essentially the underlying basis of my reasoning. Does this help explain my position?

**Draft rewrite:** This is essentially the basis of my reasoning. I could go on from here if that would help. Does this explain my position?

**Notes:** Cut wordy phrases like 'underlying basis' for plain wording. / Kept the offer to explain more, and the question at the end.

**Meaning:** ask: "Say whether this explains the sender's position"; deadline: ''; urgency: low; tone: 'neutral, formal'; implied: 'The sender can give more detail if needed.'

## 60. stanford_00059 (clear)

**Message:** What should happen if "Some Filename" and "some_filename" both exist in the same directory? And for non-empty directories "Some Dir" and "some_dir" with the same parent?

**Draft rewrite:** What should happen if "Some Filename" and "some_filename" both exist in the same directory? And for non-empty directories "Some Dir" and "some_dir" with the same parent?

**Notes:** Already clear, kept as written.

**Meaning:** ask: 'Answer what should happen in both cases: two files with the same name in one directory, and two non-empty directories with the same name under the same parent'; deadline: ''; urgency: low; tone: 'neutral, technical'; implied: ''

