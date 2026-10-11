# Worst 20: run1

Ranked by: no usable answer, then failing the grounding check, then losing to the baseline in both judge orders, then the rubric score; ties go to the lower BERTScore.

## 1. stanford_00028 (stanford)

- dropped ['2014']

**Message:** Thanks for the username change. Now, one last thingu2014since the account 'Dalahxe4st' already exists on Swedish Wikipedia and doesn't appear to have been taken over automatically, where should I go to take care of that?

**Rewrite:** Thanks for the username change. Now, one last thing: since the account 'Dalahxe4st' already exists on Swedish Wikipedia and doesn't appear to have been taken over automatically, where should I go to take care of that?

*Notes:* Fixed the typo 'one last thingu2014' to 'one last thing—'. / Kept the account name and the reason exactly as written.

BERTScore vs gold: 0.844

## 2. enron_00048 (enron)

- dropped ['Katelyn et al']

**Message:** Clarence,

EGS are asking whether Noah is yours for PRC and bonus purposes? Presumably no doubt about Katelyn et al.

What's your view. They seem happy either way. Just want clarity.

Dakota

**Rewrite:** Clarence,

EGS are asking whether Noah is yours for PRC and bonus purposes. I assume Katelyn and the others are fine either way.

What's your view? They seem happy either way. I just want clarity.

Dakota

*Notes:* Replaced "presumably" and "et al." with plain words. / Kept the question as the ask, since that is what you want from Clarence.

BERTScore vs gold: 0.848

## 3. enron_00014 (enron)

- added ['Makayla Snow\nColon & Thornton LLLP']

**Message:** Attached is a draft of an Assignment whereby ECT-PR-C, L.L.C. assigns its
rights and obligations to purchase the Class B Interest in ECT-PR-B, L.L.C. to
Condor.

Please let me have your comments. A document in the same form will be used to
transfer ECT-WR-C, L.L.C,s rights and obligations to purchase the Class B
Interest in ECT-WR-B, L.L.C. to Condor.

My direct dial is 44 [PHONE_REDACTED]

Regards.

Makayla Snow
Colon & Thornton L.L.P.
Level 16, City Tower
40 Basinghall Ho
London EC2V 5DE
Tel: +44 20 7382 0550
Fax: +44 20 7614 0012
 - 0830.wpd

**Rewrite:** Attached is a draft of an Assignment whereby ECT-PR-C, L.L.C. assigns its rights and obligations to purchase the Class B Interest in ECT-PR-B, L.L.C. to Condor.

Please let me have your comments.

A document in the same form will be used to transfer ECT-WR-C, L.L.C. rights and obligations to purchase the Class B Interest in ECT-WR-B, L.L.C. to Condor.

My direct dial is 44 [PHONE_REDACTED]

Regards.

Makayla Snow
Colon & Thornton LLLP
Level 16, City Tower
40 Basinghall Ho
London EC2V 5DE
Tel: +44 20 7382 0550
Fax: +44 20 7614 0012
 - 0830.wpd

*Notes:* Split the long sentence so the draft's purpose is easy to find. / Fixed the typo "L.L.C.\n" to "L.L.C.". / Kept the signature block and signature block exactly as written.

BERTScore vs gold: 0.867

## 4. enron_00023 (enron)

- dropped ['Kaitlin']

**Message:** The meeting is at 1:00 p.m. today. Kaitlin, if you come to my office we will walk over to Crystal's office and have the meeting there.

I have spoken to Noah and got a good data dump from him - - there is no need for him to join us this afternoon. I have the trader's name - - we should call him during our meeting.

In order to move forward we need three things:

 1. The PwC valuation of the financial contracts;
 2. A better understanding of the physical contracts and what happened;
 3. A good data dump from the trader.

Once we have this information we should approach SDGE. Let's aim at having "first contact" tomorrow morning.

**Rewrite:** The meeting is at 1:00 p.m. today.

- If you come to my office, we will walk over to Crystal's office and have the meeting there.
- I have spoken to Noah and got a good data dump from him. There is no need for him to join us this afternoon.
- I have the trader's name. We should call him during our meeting.

To move forward, we need three things:
- The PwC valuation of the financial contracts.
- A better understanding of the physical contracts and what happened.
- A good data dump from the trader.

Once we have this information, we should approach SDGE. Let's aim to have "first contact" tomorrow morning.

*Notes:* Put the meeting time and the walk first, then the three items. / Listed the three items as bullets so none is missed. / Kept "first contact" in quotes as you wrote it.

BERTScore vs gold: 0.881

## 5. enron_00004 (enron)

- dropped ['2']

**Message:** Luke, 2 things, do you have any of the letters that the producers sent to Dominion, I would like one of those AND who are you talking to at Dominion?
 
Thanks

**Rewrite:** Luke, two things:
- Do you have any of the letters the producers sent to Dominion? I would like one of those.
- Who are you talking to at Dominion?

Thanks

*Notes:* Split the two questions into bullets so both get answered. / Kept "the producers" and "Dominion" exactly as written.

BERTScore vs gold: 0.904

## 6. stanford_00024 (stanford)

- dropped ["woun't understand"]

**Message:** I can, but it is written in Lithuanian language, so I think you woun't understand. Anyway, where should I put it?

**Rewrite:** I can, but it is written in Lithuanian, so I think you won't understand. Where should I put it?

*Notes:* Removed the filler 'Anyway' so the question stands on its own. / Kept the Lithuanian detail; it is the reason for the hesitation.

BERTScore vs gold: 0.950

## 7. circa_01237 (circa)

- Circa classifier still reads the reply as indirect

**Question:** Do you like mystery novels?

**Message:** Only if it's based on real life.

**Rewrite:** Only if it's based on real life.

*Notes:* Already clear, kept as written.

BERTScore vs gold: 0.560

## 8. circa_23019 (circa)

- Circa classifier still reads the reply as indirect

**Question:** Are you interested in going to the movies?

**Message:** If there's something I haven't seen playing.

**Rewrite:** If there's something I haven't seen playing.

*Notes:* This reads as a fragment, not a full answer. Add what you're saying. / Say whether you're interested in going, and to what.

BERTScore vs gold: 0.657

## 9. circa_07172 (circa)

- Circa classifier still reads the reply as indirect
- politeness fell high -> medium

**Question:** Do you have plans after work?

**Message:** I might just go home

**Rewrite:** I might just go home.

*Notes:* Already clear, kept as written.

BERTScore vs gold: 0.707

## 10. circa_02236 (circa)

- politeness fell high -> medium

**Question:** Do you love fast life?

**Message:** I prefer slower paced

**Rewrite:** I prefer a slower pace.

*Notes:* Made the fragment a full sentence: slower paced became slower paced pace. / No reply was asked for, so none was added.

BERTScore vs gold: 0.714

## 11. stanford_00047 (stanford)

- politeness fell medium -> low

**Message:** by "without a public facing server" do you mean the kml has to be on the local machine, or that you don't want to have to bother with installing/configuring/buying a public website? And, does the custom map you want to make need to be seen by others or just you?

**Rewrite:** Two questions:
- What do you mean by "without a public facing server"? Do you mean:
  - the kml has to be on the local machine, or
- that you don't want to have to bother with installing/configuring/buying a public website?
- Does the custom map you want to make need to be seen by others, or just you?

*Notes:* Split the two questions into bullets so both get answered. / Kept your quoted phrase and the kml detail exactly as written.

BERTScore vs gold: 0.715

## 12. circa_22929 (circa)

- politeness fell medium -> low

**Question:** Is it very tiring?

**Message:** I'm pooped by the end of the day.

**Rewrite:** I'm very tired by the end of the day.

*Notes:* Replaced 'pooped' with 'tired'. / No reply is needed to this.

BERTScore vs gold: 0.730

## 13. circa_22519 (circa)

- politeness fell high -> medium

**Question:** Are you going straight home after work?

**Message:** I need to pick up some food shopping first

**Rewrite:** I need to pick up some food shopping first.

*Notes:* Already clear, kept as written.

BERTScore vs gold: 0.743

## 14. stanford_00034 (stanford)

- politeness fell medium -> low

**Message:** You are correct that the science is not copyright, but the purpose of the cite is [URL]. If I want to check your equation, where should I look?

**Rewrite:** You are correct that the science is not copyright. But the purpose of the cite is [URL]. Where should I look to check your equation?

*Notes:* Split the long sentence so the ask stands alone. / Kept [URL] exactly as written.

BERTScore vs gold: 0.818

## 15. circa_19036 (circa)

- Circa classifier still reads the reply as indirect

**Question:** Are you a fantasy fan?

**Message:** When it's about dragons.

**Rewrite:** When it's about dragons.

*Notes:* This doesn't answer the question. Add what you are saying about fantasy. / Say whether you are a fantasy fan, or what you are talking about.

BERTScore vs gold: 0.838

## 16. circa_33114 (circa)

- politeness fell high -> medium

**Question:** Do you like top 40 music?

**Message:** I like all music

**Rewrite:** I like all music.

*Notes:* Already clear, kept as written.

BERTScore vs gold: 0.885

## 17. enron_00049 (enron)

- politeness fell medium -> low

**Message:** My Tenn emails from way back.

**Rewrite:** My old Tenn emails from way back.

*Notes:* 'Way back' is vague. Add the year or date so the reader knows when. / 'Tenn' is unclear. Spell it out or name the person.

BERTScore vs gold: 0.888

## 18. enron_00047 (enron)

- politeness fell medium -> low

**Message:** i left a msg for cut rate today , have not heard back though

**Rewrite:** I left a message for Cut Rate today. I haven't heard back yet.

*Notes:* Split the run-on sentence so the message and the missing reply are separate. / Kept the name and the fact that it was today; no deadline was given.

BERTScore vs gold: 0.921

## 19. circa_07550 (circa)

- Circa classifier still reads the reply as indirect

**Question:** What would you like to visit first?

**Message:** If you don't mind I'd appreciate that.

**Rewrite:** If you don't mind, I'd appreciate that.

*Notes:* The question asks what you'd like to visit first. Your reply doesn't say which one. / Add the visit you want, and say what you'd like from them.

BERTScore vs gold: 1.000
