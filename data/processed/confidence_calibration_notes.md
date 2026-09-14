# checking if confidence score actually means anything

ran predict() on all 300 rows i hand labelled, wanted to see if the
confidence number is actually useful or just random

avg confidence when it got it right: 0.939
avg confidence when it got it wrong: 0.884

broke it down by confidence range:
  0.0-0.6:  35.7% correct (14 rows)
  0.6-0.8:  60.0% correct (15 rows)
  0.8-0.9:  70.9% correct (31 rows)
  0.9-1.0:  75.4% correct (240 rows)

ok so this is actually good - low confidence genuinely means the model
is less reliable, it's not just guessing randomly and slapping a high
number on everything. could be useful for the ui, like flag anything
under 0.6 confidence as "not sure" instead of showing it the same as
everything else

also confirms what i already knew - casual is the weak spot. did a spot
check on 20 examples and it got 0/7 casual ones right, kept calling them
neutral or terse instead. matches the full eval numbers (casual recall
was only 0.30 vs 0.87 for neutral and 0.74 for terse)
