from django.db import transaction
from dashboard.models import ClientCreditTransaction


class CreditDeductionStrategy:
    def record_transaction(
        self, wallet, amount, credits, transaction_type, status, description, reference
    ):
        return ClientCreditTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            credits=credits,
            transaction_type=transaction_type,
            status=status,
            description=description,
            reference=reference,
        )

    def deduct(self, wallet, points, description="", reference=None):
        raise NotImplementedError

    def add(self, wallet, points, description="", reference=None):
        raise NotImplementedError

    def refund(self, wallet, points, description="", reference=None):
        raise NotImplementedError


class IndiaStrategy(CreditDeductionStrategy):
    @transaction.atomic
    def deduct(self, wallet, points, description="", reference=None):
        amount = points * 25
        wallet.total_credits -= points
        wallet.total_spend += points
        wallet.save(update_fields=["total_credits", "total_spend"])

        self.record_transaction(
            wallet, amount, points, "usage", "SUC", description, reference
        )
        return amount

    @transaction.atomic
    def add(self, wallet, points, description="", reference=None):
        amount = points * 25
        wallet.total_credits += points
        wallet.total_added += points
        wallet.save(update_fields=["total_credits", "total_added"])

        self.record_transaction(
            wallet, amount, points, "purchase", "SUC", description, reference
        )
        return amount

    @transaction.atomic
    def refund(self, wallet, points, description="", reference=None):
        amount = points * 25
        wallet.total_credits += points
        wallet.total_refunded += points
        wallet.save(update_fields=["total_credits", "total_refunded"])

        self.record_transaction(
            wallet, amount, points, "refund", "SUC", description, reference
        )
        return amount


class USStrategy(CreditDeductionStrategy):
    @transaction.atomic
    def deduct(self, wallet, points, description="", reference=None):
        amount = points * 1
        wallet.total_credits -= points
        wallet.total_spend += points
        wallet.save(update_fields=["total_credits", "total_spend"])

        self.record_transaction(
            wallet, amount, points, "usage", "SUC", description, reference
        )
        return amount

    @transaction.atomic
    def add(self, wallet, points, description="", reference=None):
        amount = points * 1
        wallet.total_credits += points
        wallet.total_added += points
        wallet.save(update_fields=["total_credits", "total_added"])

        self.record_transaction(
            wallet, amount, points, "purchase", "SUC", description, reference
        )
        return amount

    @transaction.atomic
    def refund(self, wallet, points, description="", reference=None):
        amount = points * 1
        wallet.total_credits += points
        wallet.total_refunded += points
        wallet.save(update_fields=["total_credits", "total_refunded"])

        self.record_transaction(
            wallet, amount, points, "refund", "SUC", description, reference
        )
        return amount


class CreditDeductionStrategyFactory:
    COUNTRY_MAP = {
        "IN": IndiaStrategy(),
        "US": USStrategy(),
    }

    @classmethod
    def get_strategy(cls, country_code):
        return cls.COUNTRY_MAP.get(country_code, IndiaStrategy())  # fallback


class CreditDeductionService:
    @staticmethod
    def deduct_credits(org, points, country_code, description="", reference=None):
        strategy = CreditDeductionStrategyFactory.get_strategy(country_code)
        return strategy.deduct(org.wallet, points, description, reference)

    @staticmethod
    def add_credits(org, points, country_code, description="", reference=None):
        strategy = CreditDeductionStrategyFactory.get_strategy(country_code)
        return strategy.add(org.wallet, points, description, reference)

    @staticmethod
    def refund_credits(org, points, country_code, description="", reference=None):
        strategy = CreditDeductionStrategyFactory.get_strategy(country_code)
        return strategy.refund(org.wallet, points, description, reference)
