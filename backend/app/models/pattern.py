from .. import db


class Pattern(db.Model):
    """A curated pattern-library entry. The only table in the schema
    no users, user data never leaves the browser (see docs/api-contract.md).
    """

    __tablename__ = "patterns"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False)
    implies = db.Column(db.Text, nullable=False)
    why_misread = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(255), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "implies": self.implies,
            "why_misread": self.why_misread,
            "source": self.source,
        }
