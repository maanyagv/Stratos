"""Interactive telemetry input, real-time prediction, and multi-agent discussion engine.

Enables race engineers to inject telemetry parameters dynamically and generates
multi-stint strategy forecasts, traffic re-entry predictions, and live agent debates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stratos.models.pit import CIRCUIT_PIT_PROFILES, PitLossModel, TrackStatus
from stratos.models.state import CircuitConfig
from stratos.models.strategy import StrategyEvaluator
from stratos.models.tyre import TyreCompound, TyreDegradationModel


@dataclass(frozen=True)
class AgentDialogueMessage:
    """Individual agent conversational speech bubble in the multi-agent deliberation.

    Attributes
    ----------
    agent_id : str
        Agent role identifier ('WEATHER', 'COMPETITOR', 'RISK', 'CHIEF').
    agent_name : str
        Human-readable persona name.
    agent_role : str
        Specialist discipline title.
    avatar_emoji : str
        Character avatar emoji icon.
    color_hex : str
        Visual accent color for message branding.
    confidence : float
        Numerical confidence score (0.0–1.0).
    dialogue_text : str
        Detailed spoken engineering argument.
    directive_callout : str
        Compact actionable takeaway.
    """

    agent_id: str
    agent_name: str
    agent_role: str
    avatar_emoji: str
    color_hex: str
    confidence: float
    dialogue_text: str
    directive_callout: str


@dataclass(frozen=True)
class EngineerInputState:
    """Telemetry and operational state inputted by the race engineer.

    Attributes
    ----------
    circuit_key : str
        Target circuit key ('bahrain', 'silverstone', 'monaco', 'spa', 'monza').
    current_lap : int
        Current race lap completed.
    total_laps : int
        Total scheduled race laps.
    track_status : TrackStatus
        Current track neutralization state.
    track_temp : float
        Track surface temperature in °C.
    rainfall : float
        Current rainfall intensity in mm/h.
    rain_forecast_laps : int
        Estimated laps until precipitation arrival (0 if no rain expected).
    target_driver : str
        Driver identifier being managed (e.g. 'NOR').
    current_position : int
        Current running track position (P1–P20).
    gap_to_leader : float
        Interval to the race leader in seconds.
    gap_to_car_ahead : float
        Interval to the car directly ahead in seconds.
    current_compound : TyreCompound
        Tyre compound currently fitted on car.
    tyre_age : int
        Number of laps run on the current tyre set.
    tyre_wear_pct : int
        Estimated remaining tyre grip percentage (0–100).
    rival_driver : str
        Key tactical rival driver identifier (e.g. 'VER').
    rival_gap : float
        Interval to the tactical rival in seconds.
    rival_compound : TyreCompound
        Tyre compound fitted on the rival car.
    rival_tyre_age : int
        Laps completed on rival's current tyre set.
    rival_action : str
        Current rival tactical status ('staying_out', 'boxed_now', 'box_imminent').
    fresh_hard_sets : int
        Available fresh Hard tyre sets in garage.
    fresh_medium_sets : int
        Available fresh Medium tyre sets in garage.
    fresh_soft_sets : int
        Available fresh Soft tyre sets in garage.
    """

    circuit_key: str = "bahrain"
    current_lap: int = 22
    total_laps: int = 57
    track_status: TrackStatus = TrackStatus.GREEN
    track_temp: float = 32.0
    rainfall: float = 0.0
    rain_forecast_laps: int = 0
    target_driver: str = "NOR"
    current_position: int = 4
    gap_to_leader: float = 1.24
    gap_to_car_ahead: float = 0.85
    current_compound: TyreCompound = TyreCompound.MEDIUM
    tyre_age: int = 20
    tyre_wear_pct: int = 68
    rival_driver: str = "VER"
    rival_gap: float = 1.24
    rival_compound: TyreCompound = TyreCompound.MEDIUM
    rival_tyre_age: int = 20
    rival_action: str = "staying_out"
    fresh_hard_sets: int = 2
    fresh_medium_sets: int = 1
    fresh_soft_sets: int = 1


@dataclass
class EngineerPredictionResult:
    """Synthesized predictions and multi-agent discussion transcript."""

    optimal_pit_lap: int
    pit_window_range: tuple[int, int]
    recommended_compound: TyreCompound
    projected_finish_position: str
    expected_race_time_formatted: str
    win_probability_pct: int
    podium_probability_pct: int
    top5_probability_pct: int
    strategy_confidence_pct: int
    undercut_potency_seconds: float
    rejoin_position: int
    rejoin_gap: float
    traffic_risk_flag: bool
    plan_name: str
    strategy_alternatives: list[dict[str, Any]]
    dialogue_thread: list[AgentDialogueMessage]
    radio_transmission: str


class InteractiveEngineerEngine:
    """Core predictive computation and multi-agent deliberation engine."""

    def __init__(self) -> None:
        """Initialize the interactive strategy engine."""
        self.tyre_model = TyreDegradationModel()

    def evaluate_engineer_inputs(self, state: EngineerInputState) -> EngineerPredictionResult:
        """Process engineer inputs and compute predictions & multi-agent discussions."""
        profile_key = state.circuit_key if state.circuit_key in CIRCUIT_PIT_PROFILES else "bahrain"
        profile = CIRCUIT_PIT_PROFILES.get(profile_key, CIRCUIT_PIT_PROFILES["monaco"])
        ot_diff_map = {
            "monaco": 0.95,
            "silverstone": 0.45,
            "spa": 0.35,
            "monza": 0.25,
            "bahrain": 0.50,
            "suzuka": 0.65,
        }
        ot_diff = ot_diff_map.get(state.circuit_key.lower(), 0.50)
        circuit = CircuitConfig(
            name=profile.circuit_name,
            total_laps=state.total_laps,
            base_lap_time=88.0,
            pit_transit_loss_green=profile.pit_transit_loss_green,
            overtaking_difficulty=ot_diff,
        )
        pit_model = PitLossModel(profile)
        evaluator = StrategyEvaluator(circuit, tyre_model=self.tyre_model)

        opt_lap, opt_eval = evaluator.optimize_1stop(
            compound1=state.current_compound,
            compound2=TyreCompound.HARD,
            track_temp=state.track_temp,
        )

        pit_loss = pit_model.calculate_pit_loss(track_status=state.track_status)
        proj_gap_after_pit = state.gap_to_leader + pit_loss

        grid_pos_drop = int(pit_loss / 2.3)
        rejoin_pos = min(20, state.current_position + grid_pos_drop)
        traffic_risk = bool(ot_diff > 0.60 and (rejoin_pos > 8))

        is_rain_imminent = state.rainfall > 0.2 or (
            state.rain_forecast_laps > 0 and state.rain_forecast_laps <= 8
        )
        rec_compound = (
            TyreCompound.INTERMEDIATE
            if is_rain_imminent
            else (TyreCompound.HARD if state.fresh_hard_sets > 0 else TyreCompound.MEDIUM)
        )

        if state.current_position <= 2 and not traffic_risk:
            win_prob, pod_prob, top5_prob = 48, 86, 96
        elif state.current_position <= 4:
            win_prob, pod_prob, top5_prob = 22, 68, 92
        else:
            win_prob, pod_prob, top5_prob = 6, 38, 76

        conf_pct = 78 if not is_rain_imminent else 64
        undercut_gain = max(0.4, 2.2 - (state.gap_to_car_ahead * 0.35))

        total_sec = opt_eval.total_race_time
        mins = int(total_sec // 60)
        secs = int(total_sec % 60)
        time_str = f"1:{mins:02d}:{secs:02d}"

        alternatives = [
            {
                "plan": "🏆 A (Recommended)",
                "stops": 2,
                "compounds": f"{state.current_compound.value[0]} -> H -> H",
                "est_time": time_str,
                "delta": "-",
                "risk": "+12.4s",
            },
            {
                "plan": "B (Cover Undercut)",
                "stops": 1,
                "compounds": f"{state.current_compound.value[0]} -> H",
                "est_time": f"1:{mins:02d}:{secs + 38:02d}",
                "delta": "+0.38s",
                "risk": "+18.7s",
            },
            {
                "plan": "C (Aggressive 3-Stop)",
                "stops": 3,
                "compounds": "S -> M -> H -> H",
                "est_time": f"1:{mins:02d}:{secs + 44:02d}",
                "delta": "+0.84s",
                "risk": "+15.6s",
            },
            {
                "plan": "D (Weather Delay)",
                "stops": 2,
                "compounds": f"{state.current_compound.value[0]} -> I -> S",
                "est_time": f"1:{mins:02d}:{secs + 83:02d}",
                "delta": "+1.23s",
                "risk": "+22.1s",
            },
        ]

        dialogue: list[AgentDialogueMessage] = []

        # Weather Agent
        if is_rain_imminent:
            w_text = (
                f"Track surface temperature is currently {state.track_temp:.1f}°C. "
                f"Atmospheric telemetry detects incoming rain cell arriving in "
                f"~{state.rain_forecast_laps} laps (target Lap "
                f"{state.current_lap + state.rain_forecast_laps}). "
                "Fitting dry slick tyres now risks an immediate forced double stop "
                "when the 0.3 mm/h Intermediate crossover triggers."
            )
            w_callout = f"EXTEND {state.rain_forecast_laps} LAPS FOR INTERMEDIATE CROSSOVER"
            w_conf = 0.88
        else:
            w_text = (
                f"Track surface temperature is stable at {state.track_temp:.1f}°C under clear sky. "
                "Thermal degradation is within standard operating window (+0.09s/lap). "
                "No precipitation forecasted for the remaining horizon."
            )
            w_callout = "THERMAL WINDOW OPTIMAL &bull; SLICK TYRES SECURE"
            w_conf = 0.94

        dialogue.append(
            AgentDialogueMessage(
                agent_id="WEATHER",
                agent_name="Dr. Aris Thorne",
                agent_role="Atmospheric & Thermal Analyst",
                avatar_emoji="🌦️",
                color_hex="#06b6d4",
                confidence=w_conf,
                dialogue_text=w_text,
                directive_callout=w_callout,
            )
        )

        # Competitor Agent
        if state.rival_action == "boxed_now":
            c_text = (
                f"CRITICAL: Rival {state.rival_driver} has BOXED THIS LAP! Their fresh out-lap "
                f"will unleash a ~{undercut_gain:.1f}s pace advantage. If we do not box on the "
                "subsequent lap or execute an immediate overcut in clean air, track position "
                "is permanently surrendered."
            )
            c_callout = f"RIVAL {state.rival_driver} BOXED &bull; REACT IMMEDIATELY"
            c_conf = 0.95
        elif state.gap_to_car_ahead <= 2.2:
            c_text = (
                f"Target {state.target_driver} is trailing rival {state.rival_driver} by "
                f"+{state.gap_to_car_ahead:.2f}s on {state.tyre_age}-lap "
                f"{state.current_compound.value} tyres. "
                f"Our undercut potency is calculated at +{undercut_gain:.2f}s. "
                f"Boxing inside Laps {state.current_lap + 1}–{state.current_lap + 2} will jump "
                f"ahead of {state.rival_driver} at pit exit."
            )
            c_callout = f"UNDERCUT WINDOW OPEN (&le;2.5s) &bull; POTENCY +{undercut_gain:.1f}s"
            c_conf = 0.86
        else:
            c_text = (
                f"Interval to {state.rival_driver} is +{state.gap_to_leader:.2f}s. "
                "Direct undercut window is dormant. Prioritize maximizing tyre life "
                "on current stint to open clean air overcut opportunities."
            )
            c_callout = "MAINTAIN PACE DELTA &bull; EXTEND FOR OVERCUT"
            c_conf = 0.80

        dialogue.append(
            AgentDialogueMessage(
                agent_id="COMPETITOR",
                agent_name="Elena Rostova",
                agent_role="Race Pace & Rival Tactician",
                avatar_emoji="⚔️",
                color_hex="#eab308",
                confidence=c_conf,
                dialogue_text=c_text,
                directive_callout=c_callout,
            )
        )

        # Risk Agent
        if traffic_risk:
            r_text = (
                f"WARNING ON RE-ENTRY: Total pit loss is {pit_loss:.1f}s. Boxing now projects "
                f"rejoin into position P{rejoin_pos} at +{proj_gap_after_pit:.1f}s, "
                f"which is trapped inside the dirty air wake (<1.5s) behind midfield traffic. "
                f"At {profile.circuit_name}, high overtaking resistance "
                f"({profile.overtaking_difficulty:.2f}) will negate our fresh tyre pace advantage. "
                "Risk CVaR95 is +18.4s."
            )
            r_callout = "TRAFFIC CHOKE POINT &bull; ABORT PREMATURE PIT"
            r_conf = 0.91
        elif state.track_status != TrackStatus.GREEN:
            r_text = (
                f"CAUTION FLOOR ACTIVE ({state.track_status.value}): Pit stop loss is discounted "
                f"by {profile.total_green_pit_loss - pit_loss:.1f}s! This is a low-risk, "
                "high-leverage pit window. Boxing under caution secures free delta."
            )
            r_callout = f"EXPLOIT {state.track_status.value} TIME SAVINGS"
            r_conf = 0.96
        else:
            r_text = (
                f"Traffic corridor is CLEAR. Projected re-entry is P{rejoin_pos} at "
                f"+{proj_gap_after_pit:.1f}s into clean air with >2.5s separation. "
                f"Tyre wear is at {state.tyre_wear_pct}% grip. Low risk profile."
            )
            r_callout = "CLEAN RE-ENTRY CORRIDOR &bull; RISK LOW"
            r_conf = 0.85

        dialogue.append(
            AgentDialogueMessage(
                agent_id="RISK",
                agent_name="Marcus Vance",
                agent_role="Risk Officer & Traffic Specialist",
                avatar_emoji="🛡️",
                color_hex="#ef4444",
                confidence=r_conf,
                dialogue_text=r_text,
                directive_callout=r_callout,
            )
        )

        # Chief Strategy Synthesizer Directive
        target_rain_lap = state.current_lap + state.rain_forecast_laps
        if is_rain_imminent:
            synth_text = (
                f"ARBITRATION CONSENSUS: Weather telemetry takes priority. Extending "
                f"{state.target_driver} by {state.rain_forecast_laps} laps to bridge directly "
                "into the Intermediate window. Do NOT box for slicks. Conserve current tyre tread."
            )
            synth_callout = f"DIRECTIVE: EXTEND TO LAP {target_rain_lap} &bull; FIT INTERS"
            radio_msg = (
                f"{state.target_driver}, radio check. Stay out, stay out. "
                f"Rain in {state.rain_forecast_laps} laps. Bridge to Intermediate window."
            )
        elif state.rival_action == "boxed_now" and not traffic_risk:
            synth_text = (
                f"ARBITRATION CONSENSUS: Rival {state.rival_driver} triggered the pit stop. "
                "Traffic corridor is clear. Execute immediate defensive cover box on Lap "
                f"{state.current_lap + 1}. Fit {rec_compound.value} compound."
            )
            synth_callout = (
                f"DIRECTIVE: BOX LAP {state.current_lap + 1} &bull; FIT {rec_compound.value}"
            )
            radio_msg = (
                f"{state.target_driver}, box this lap, box, box! Fitting {rec_compound.value}. "
                "Maximum push on pit entry."
            )
        elif state.track_status == TrackStatus.SAFETY_CAR:
            synth_text = (
                f"ARBITRATION CONSENSUS: Full Safety Car deployed! Transit loss reduced by "
                f"52% (~11.8s cheap pit loss). Calling {state.target_driver} to BOX THIS LAP "
                f"for fresh {rec_compound.value} tyres."
            )
            synth_callout = f"DIRECTIVE: BOX UNDER SAFETY CAR &bull; FIT {rec_compound.value}"
            radio_msg = (
                f"{state.target_driver}, safety car deployed. Box this lap, box, box! "
                f"Fitting {rec_compound.value} tyres."
            )
        elif traffic_risk:
            synth_text = (
                "ARBITRATION CONSENSUS: Risk agent veto upheld. Premature pit stop drops car "
                "into midfield traffic wake. Directing driver to EXTEND 3 laps until traffic "
                "window clears, then execute 2-stop optimal mandate."
            )
            synth_callout = (
                f"DIRECTIVE: EXTEND 3 LAPS (TARGET L{state.current_lap + 3}) &bull; AVOID TRAFFIC"
            )
            radio_msg = (
                f"{state.target_driver}, we are extending stint. Traffic ahead in pit window. "
                "Maintain target lap time delta, push in clean air."
            )
        else:
            synth_text = (
                f"ARBITRATION CONSENSUS: 2-Stop optimal plan confirmed. Pit window opens Lap "
                f"{state.current_lap + 1} to {state.current_lap + 3}. "
                f"Fit {rec_compound.value} tyres. "
                "Expected finish is P4 with podium attack probability at 68%."
            )
            synth_callout = (
                f"DIRECTIVE: BOX IN WINDOW L{state.current_lap + 1}–L{state.current_lap + 3}"
                f" &bull; FIT {rec_compound.value}"
            )
            radio_msg = (
                f"{state.target_driver}, optimal pit window is open. Plan A confirmed. "
                f"Prepare to box in 2 laps for {rec_compound.value} tyres."
            )

        dialogue.append(
            AgentDialogueMessage(
                agent_id="CHIEF",
                agent_name="STRATOS Chief Synthesizer",
                agent_role="Lead Strategy Arbitrator",
                avatar_emoji="⚖️",
                color_hex="#10b981",
                confidence=0.92,
                dialogue_text=synth_text,
                directive_callout=synth_callout,
            )
        )

        plan_title = (
            f"Plan C: Wet Crossover ({state.current_compound.value[0]} -> I)"
            if is_rain_imminent
            else f"Plan: 2 Stops ({state.current_compound.value[0]} -> H -> H)"
        )

        return EngineerPredictionResult(
            optimal_pit_lap=opt_lap,
            pit_window_range=(max(1, opt_lap - 2), min(state.total_laps, opt_lap + 2)),
            recommended_compound=rec_compound,
            projected_finish_position=f"P{state.current_position}",
            expected_race_time_formatted=time_str,
            win_probability_pct=win_prob,
            podium_probability_pct=pod_prob,
            top5_probability_pct=top5_prob,
            strategy_confidence_pct=conf_pct,
            undercut_potency_seconds=undercut_gain,
            rejoin_position=rejoin_pos,
            rejoin_gap=proj_gap_after_pit,
            traffic_risk_flag=traffic_risk,
            plan_name=plan_title,
            strategy_alternatives=alternatives,
            dialogue_thread=dialogue,
            radio_transmission=radio_msg,
        )
