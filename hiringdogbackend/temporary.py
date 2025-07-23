def populate_next_round_to_existing_candidate_data():
    from dashboard.models import Candidate, JobInterviewRounds

    candidates = Candidate.objects.select_related(
        "last_completed_round", "designation", "next_round"
    ).all()

    rounds_to_update = []
    for candidate in candidates:
        if candidate.last_completed_round:
            next_round = (
                JobInterviewRounds.objects.filter(
                    job=candidate.designation,
                    sequence_number__gt=candidate.last_completed_round.sequence_number,
                )
                .order_by("sequence_number")
                .first()
            )
            rounds_to_update.append(Candidate(id=candidate.id, next_round=next_round))
        elif not candidate.last_completed_round:
            initial_round = (
                JobInterviewRounds.objects.filter(job=candidate.designation)
                .order_by("sequence_number")
                .first()
            )
            rounds_to_update.append(
                Candidate(id=candidate.id, next_round=initial_round)
            )

    Candidate.objects.bulk_update(rounds_to_update, ["next_round"])
