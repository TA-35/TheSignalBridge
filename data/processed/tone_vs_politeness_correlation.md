# tone vs politeness correlation check

matched 286 unique messages between my eval set and yvonne's politeness scores

r = 0.199, p = 0.0007

weak correlation but statistically significant (p < 0.001, not noise). this
confirms tone and politeness are separable signals - a message can be
casual and polite, or formal and rude, so the two models aren't just
duplicating each other's comment to the llm. matches what the design doc
called for when it split these into two categories in the first place.
