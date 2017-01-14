from harpoon.formatter import MergedOptionStringFormatter
from harpoon.errors import BadSpecValue, BadOption
from option_merge_passwords import Variable
from harpoon.actions import an_action

from option_merge_addons import option_merge_addon_hook
from input_algorithms import spec_base as sb
from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions

from marathon.models import MarathonApp
from marathon import MarathonClient
import subprocess
import logging
import time
import json
import six

log = logging.getLogger("mesos_harpoon_crosshair")

########################
###   ADDON HOOK
########################

@option_merge_addon_hook(extras=[("option_merge.addons", "password_manager")])
def register_specs(collector, result_maker, **kwargs):
    return result_maker(specs={(0, "mesos"): sb.required(Mesos.FieldSpec(formatter=MergedOptionStringFormatter))})

@option_merge_addon_hook(post_register=True)
def register_tasks(collector, task_maker, **kwargs):
    task_maker("deploy_to_mesos", label="Mesos")
    task_maker("show_mesos_config", label="Mesos")

########################
###   ACTIONS
########################

def get_mesos_from_config(collector, image, artifact):
    if artifact in (None, ""):
        artifact = sb.NotSpecified

    if artifact is sb.NotSpecified:
        raise BadOption("Please specify what environment you want with --artifact")

    collector.configuration.update({"mesos": {"environment_name": artifact}})
    env = collector.configuration.get(["mesos", "envs"], ignore_converters=True)
    if env is not None:
        env = env.as_dict(ignore_converters=True)
        if artifact in env:
            collector.configuration.update({"mesos": env[artifact]})

    return collector.configuration["mesos"]

@an_action(needs_image=True)
def show_mesos_config(collector, image, artifact, **kwargs):
    """Show the mesos config"""
    mesos = get_mesos_from_config(collector, image, artifact)
    print("Mesos is at {0}".format(mesos.mesos_url))

    def serializer(o):
        if type(o) is Variable:
            if o.type == "plain":
                return o.resolve()
            else:
                return "<redacted>"
        raise TypeError(repr(o) + " is not JSON serializable")

    print(json.dumps(mesos.config, sort_keys=True, indent=4, default=serializer))
    return mesos

@an_action(needs_image=True)
def deploy_to_mesos(collector, image, artifact, **kwargs):
    """Deploy an image to mesos"""
    mesos = get_mesos_from_config(collector, image, artifact)

    def serializer(o):
        if type(o) is Variable:
            return o.resolve()
        raise TypeError(repr(o) + " is not JSON serializable")

    c = MarathonClient(mesos.mesos_url)

    apps = c.list_apps()
    wanted = ["/{0}".format(name) for name in mesos.deployments]

    found = {}
    for app in apps:
        if app.id in wanted:
            found[app.id[1:]] = app

    deployment_ids = {}
    for name, deployment in mesos.deployments.items():
        existing = found.get(name)
        config = json.loads(json.dumps(deployment.config.as_dict(), default=serializer))
        config["id"] = name

        if existing is None:
            app = MarathonApp(**config)
            res = c.create_app(name, app)
        else:
            app = existing
            for key, val in config.items():
                setattr(app, key, val)
            res = c.update_app(name, app)

        deployment_ids[name] = res["deploymentId"]

    while True:
        deployments = c.list_deployments()

        found = False
        for d in deployments:
            if d.id in deployment_ids.values():
                log.info("Waiting on deployment (%s)", d.id)
                for step in d.steps:
                    log.info("\t{0}".format(repr(step)))
                found = True

        if not found:
            break

        time.sleep(1)

    log.info("Finished deploying!")

########################
###   SPECS
########################

class an_image_spec(sb.Spec):
    def normalise_filled(self, meta, val):
        val = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter).normalise(meta, val)
        if not isinstance(val, six.string_types):
            if val.image_index is sb.NotSpecified:
                raise BadSpecValue("Specified image has no image_index option!", image=val.name)
            val = val.image_name
        return val

########################
###   OBJECTS
########################

class Deployment(dictobj.Spec):
    cmd = dictobj.Field(sb.string_spec, wrapper=sb.required)
    use_revision_tag = dictobj.Field(sb.boolean, default=False)
    application_options = dictobj.Field(sb.dictionary_spec, wrapper=sb.optional_spec)
    docker_image = dictobj.Field(an_image_spec)
    mount_dev_log = dictobj.Field(sb.boolean, default=False)

    @property
    def config(self):
        base = {"cmd": self.cmd}
        container = {"container": {"type": "DOCKER", "docker": {"image": self.docker_image}}}
        if self.use_revision_tag:
            tag = self.use_revision_tag
            if tag is True:
                tag = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
            container["container"]["docker"]["image"] = "{0}:{1}".format(container["container"]["docker"]["image"], tag)

        if self.mount_dev_log:
            container["container"]["docker"]["volumes"] = {"containerPath": "/dev/log", "hostPoath": "/dev/log", "mode": "RW"}

        application_options = self.application_options
        if application_options is sb.NotSpecified:
            application_options = {}

        return MergedOptions.using(base, container, self.application_options)

class Mesos(dictobj.Spec):
    mesos_url = dictobj.Field(sb.string_spec, wrapper=sb.required)
    check_image_exists = dictobj.Field(sb.boolean, default=True)
    deployments = dictobj.Field(sb.dictof(sb.string_spec(), Deployment.FieldSpec(formatter=MergedOptionStringFormatter)))
    environment_name = dictobj.Field(sb.string_spec, wrapper=sb.required)
