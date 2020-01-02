import logging
import warnings
import json
import os
import typing
from typing import Any, List, Text, Optional

import rasa.utils.io

from rasa.core.actions.action import (
    ACTION_BACK_NAME,
    ACTION_LISTEN_NAME,
    ACTION_RESTART_NAME,
    ACTION_SESSION_START_NAME,
)
from rasa.core.constants import (
    USER_INTENT_BACK,
    USER_INTENT_RESTART,
    USER_INTENT_SESSION_START,
)
from rasa.core.domain import Domain, InvalidDomain
from rasa.core.events import ActionExecuted
from rasa.core.policies.policy import Policy
from rasa.core.trackers import DialogueStateTracker
from rasa.core.constants import MAPPING_POLICY_PRIORITY

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Action
from rasa_sdk.events import SlotSet


if typing.TYPE_CHECKING:
    from rasa.core.policies.ensemble import PolicyEnsemble

import coco


logger = logging.getLogger(__name__)


class CoCoMappingPolicy(Policy):
    """Policy which maps intents directly to actions.

    Intents can be assigned components in the domain file which are to be
    executed whenever the intent is detected. This policy takes precedence over
    any other policy."""

    @staticmethod
    def _standard_featurizer() -> None:
        return None

    def __init__(self, priority: int = 6) -> None:
        """Create a new Mapping policy."""

        super().__init__(priority=priority)

    @classmethod
    def validate_against_domain(
        cls, ensemble: Optional["PolicyEnsemble"], domain: Optional[Domain]
    ) -> None:
        if not domain:
            return

        has_mapping_policy = ensemble is not None and any(
            isinstance(p, cls) for p in ensemble.policies
        )
        has_triggers_in_domain = any(
            [
                "triggers" in properties
                for intent, properties in domain.intent_properties.items()
            ]
        )
        if has_triggers_in_domain and not has_mapping_policy:
            raise InvalidDomain(
                "You have defined triggers in your domain, but haven't "
                "added the MappingPolicy to your policy ensemble. "
                "Either remove the triggers from your domain or "
                "exclude the MappingPolicy from your policy configuration."
            )

    def train(
        self,
        training_trackers: List[DialogueStateTracker],
        domain: Domain,
        **kwargs: Any,
    ) -> None:
        """Does nothing. This policy is deterministic."""

        pass

    def predict_action_probabilities(
        self, tracker: DialogueStateTracker, domain: Domain
    ) -> List[float]:
        """Predicts the assigned action.

        If the current intent is assigned to an action that action will be
        predicted with the highest probability of all policies. If it is not
        the policy will predict zero for every action."""

        prediction = [0.0] * domain.num_actions
        active_component = tracker.slots.get("active_component").value
        # if active_component:
        #     idx = domain.index_for_action(active_component)
        #     prediction[idx] = 1
        if tracker.latest_action_name == ACTION_LISTEN_NAME:
            if active_component:
                idx = domain.index_for_action(active_component)
                if idx is None:
                    warnings.warn(
                        "MappingPolicy tried to predict unknown "
                        f"action '{active_component}'. Make sure all mapped actions are "
                        "listed in the domain."
                    )
                else:
                    prediction[idx] = 1

            if any(prediction):
                logger.debug(
                    "Continue component exec"
                    " '{}' in the domain."
                    "".format(active_component)
                )
        elif tracker.latest_action_name == active_component and active_component is not None:
            latest_action = tracker.get_last_event_for(ActionExecuted)
            assert latest_action.action_name == active_component
            if latest_action.policy and latest_action.policy.endswith(
                type(self).__name__
            ):
                # this ensures that we only predict listen, if we predicted
                # the mapped action
                logger.debug(
                    "The mapped action, '{}', for this intent, '{}', was "
                    "executed last so MappingPolicy is returning to "
                    "action_listen.".format(active_component, "")
                )

                idx = domain.index_for_action(ACTION_LISTEN_NAME)
                prediction[idx] = 1
            else:
                logger.debug(
                    "The mapped action, '{}', for this intent, '{}', was "
                    "executed last, but it was predicted by another policy, '{}', so MappingPolicy is not"
                    "predicting any action.".format(
                        active_component, "", latest_action.policy
                    )
                )
        else:
            logger.debug(
                "There is no mapped action for the predicted intent, "
                "'{}'.".format("")
            )
        return prediction

    def persist(self, path: Text) -> None:
        """Only persists the priority."""

        config_file = os.path.join(path, "coco_mapping_policy.json")
        meta = {"priority": self.priority}
        rasa.utils.io.create_directory_for_file(config_file)
        rasa.utils.io.dump_obj_as_json_to_file(config_file, meta)

    @classmethod
    def load(cls, path: Text) -> "CoCoMappingPolicy":
        """Returns the class with the configured priority."""

        meta = {}
        if os.path.exists(path):
            meta_path = os.path.join(path, "coco_mapping_policy.json")
            if os.path.isfile(meta_path):
                meta = json.loads(rasa.utils.io.read_file(meta_path))

        return cls(**meta)


def coco_run(component_name, dispatcher: CollectingDispatcher, tracker: Tracker, domain):
    coco_in_context = {
        slot_name: slot 
        for slot_name, slot in tracker.slots.items()
        if slot
        }
    coco_resp = coco.exchange(
        component_name,
        tracker.sender_id,
        user_input=tracker.latest_message.get("text", None),
        context=coco_in_context,
        flatten_context=True
    )
    returned_slots = [
        SlotSet(context_key, context_value) 
        for context_key, context_value in coco_resp.updated_context.items()]
    dispatcher.utter_message(coco_resp.response)
    active_component = component_name if not coco_resp.component_done else ""
    return [SlotSet("active_component", active_component)] + returned_slots

class GenericCoCoAction(Action):
    component_name = "generic_coco"
    def name(self):
        return self.component_name
    
    def run(self, dispatcher, tracker, domain):
        return coco_run(self.component_name, dispatcher, tracker, domain)