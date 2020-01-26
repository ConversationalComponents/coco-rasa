
# A Toolkit to work with components in rasa

### Installation (We recommend using a virtualenv):
```
pip install coco-rasa
```

### Setup:
#### Setting up CoCo actions
in actions.py
```python
from coco_rasa import GenericCoCoAction

class OneLiners(GenericCoCoAction):
    # component name is the component_id from CoCo marketplace
    component_name = "generic_oneliners_vp3"

class Namer(GenericCoCoAction):
    component_name = "namer_vp3"
```

in domain.yml
```yaml
actions:
    - generic_oneliners_vp3
    - namer_vp3
```

#### to enable multi-turn capabilities for CoCo actions
in your rasa bot config.yml
```yaml
policy:
  - name: "coco_rasa.CoCoContextPolicy"
```

#### triggering actions (and CoCo actions)
* MappingPolicy

``` yaml
# config.yml:
policies:
    - name: MappingPolicy
```

```yaml
# domain.yml
intents:
    - greet:
        triggers: namer_vp3
    - someotherintent
```
* Fallback policy

``` yaml
# config.yaml
policies:
    - name: "FallbackPolicy"
        nlu_threshold: 0.4
        core_threshold: 0.3
        fallback_action_name: "generic_oneliners_vp3"
```

#### using context transfer
in domain.yml declare the keys you want the use(from CoCo context transfer protocol). data will be transferred automatically between components.
```yaml
slots:
  user.firstName:
    type: text
  user.lastName:
    type: text
```