# Rating the Compose rewrites

Each row is one original message (with the question it answers, for Circa replies) and one rewrite of it, with the rewrite's notes and the meaning it extracted. Score the rewrite against the original only - there is no reference answer - and don't try to work out which model wrote it. Put 0, 1 or 2 in each of the four score columns; the comment is optional. Rate on your own, and don't open key.json until you've finished: it says which model wrote each row.

Score each criterion 0, 1 or 2:
- meaning_kept: 2 = same meaning, nothing added or dropped (stating the answer a reply to a question clearly implies is not an addition); 1 = a small detail changed or added; 0 = a fact, commitment, deadline or urgency changed, or information was invented (including an answer the reply does not settle).
- clarity: 2 = main ask first, literal language, several asks each on their own line, and for a reply to a question the answer it implies stated; 1 = mostly clear but one ask buried, an idiom left in, or a reply's implied answer left for the reader to work out; 0 = ask buried, asks run together, or a clear message needlessly rewritten.
- warmth: 2 = keeps greetings, thanks and courtesy, reads friendly; 1 = a little flat; 0 = cold, curt or robotic where the original was friendly.
- notes_accurate: 2 = notes correctly describe the changes made; 1 = a note is vague; 0 = a note is wrong or describes a change that was not made.
