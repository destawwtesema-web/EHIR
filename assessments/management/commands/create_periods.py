from django.core.management.base import BaseCommand

from assessments.models import AssessmentPeriod


class Command(BaseCommand):
    help = "Create Ethiopian assessment reporting periods."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            required=True,
            help="Ethiopian reporting year, e.g. 2018",
        )

    def handle(self, *args, **options):

        year = options["year"]

        periods = []

        # -------------------------
        # Monthly periods
        # -------------------------

        for month in range(1, 13):

            periods.append(
                {
                    "period_type": AssessmentPeriod.PeriodType.MONTHLY,
                    "period_number": month,
                    "name": f"Month {month}",
                    "start_month": month,
                    "end_month": month,
                }
            )

        # -------------------------
        # Quarterly periods
        # -------------------------

        quarters = [
            (1, "Quarter 1", 1, 3),
            (2, "Quarter 2", 4, 6),
            (3, "Quarter 3", 7, 9),
            (4, "Quarter 4", 10, 12),
        ]

        for number, name, start, end in quarters:

            periods.append(
                {
                    "period_type": AssessmentPeriod.PeriodType.QUARTERLY,
                    "period_number": number,
                    "name": name,
                    "start_month": start,
                    "end_month": end,
                }
            )

        # -------------------------
        # Biannual periods
        # -------------------------

        biannual = [
            (1, "First Half", 1, 6),
            (2, "Second Half", 7, 12),
        ]

        for number, name, start, end in biannual:

            periods.append(
                {
                    "period_type": AssessmentPeriod.PeriodType.BIANNUAL,
                    "period_number": number,
                    "name": name,
                    "start_month": start,
                    "end_month": end,
                }
            )

        # -------------------------
        # Annual period
        # -------------------------

        periods.append(
            {
                "period_type": AssessmentPeriod.PeriodType.ANNUAL,
                "period_number": 1,
                "name": "Annual",
                "start_month": 1,
                "end_month": 12,
            }
        )

        created = 0
        existing = 0

        for data in periods:

            period, was_created = (
                AssessmentPeriod.objects.get_or_create(
                    year=year,
                    period_type=data["period_type"],
                    period_number=data["period_number"],
                    defaults={
                        "name": data["name"],
                        "start_month": data["start_month"],
                        "end_month": data["end_month"],
                        "active": True,
                    },
                )
            )

            if was_created:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created: {period}"
                    )
                )
            else:
                existing += 1
                self.stdout.write(
                    f"Already exists: {period}"
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Created={created}, Existing={existing}"
            )
        )