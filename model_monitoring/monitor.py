# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: This code is generated as part of the AutoMLOps output.

"""Creates a Model Monitoring Job in Vertex AI for a deployed model endpoint."""

import argparse
import json
import pprint as pp
import subprocess
import yaml

from google.cloud import aiplatform
from google.cloud.aiplatform import model_monitoring
from google.cloud import logging
from google.cloud import storage

def execute_process(command: str, to_null: bool):
    """Executes an external shell process.

    Args:
        command: The string of the command to execute.
        to_null: Determines where to send output.
    Raises:
        Exception: If an error occurs in executing the script.
    """
    stdout = subprocess.DEVNULL if to_null else None
    try:
        subprocess.run([command],
                       shell=True,
                       check=True,
                       stdout=stdout,
                       stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f'Error executing process. {err}') from err


def write_file(filepath: str, text: str, mode: str):
    """Writes a file at the specified path. Defaults to utf-8 encoding.

    Args:
        filepath: Path to the file.
        text: Text to be written to file.
        mode: Read/write mode to be used.
    Raises:
        Exception: If an error is encountered writing the file.
    """
    try:
        with open(filepath, mode, encoding='utf-8') as file:
            file.write(text)
        file.close()
    except OSError as err:
        raise OSError(f'Error writing to file. {err}') from err


def upload_automatic_retraining_parameters(
        auto_retraining_params: dict,
        gs_auto_retraining_params_path: str,
        gs_pipeline_job_spec_path: str,
        storage_bucket_name: str):
    """Upload automatic pipeline retraining params from local to GCS

    Args:
        auto_retraining_params: Pipeline parameter values to use when retraining the model.
        gs_auto_retraining_params_path: GCS path of the retraining parameters.
        gs_pipeline_job_spec_path: The GCS path of the pipeline job spec.
        storage_bucket_name: Name of the storage bucket to write to.
    """
    auto_retraining_params['gs_pipeline_spec_path'] = gs_pipeline_job_spec_path
    serialized_params = json.dumps(auto_retraining_params, indent=4)
    write_file('model_monitoring/automatic_retraining_parameters.json',
               serialized_params, 'w')

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(storage_bucket_name)
    filename = '/'.join(gs_auto_retraining_params_path.split('/')[3:])
    blob = bucket.blob(filename)
    blob.upload_from_filename(
        'model_monitoring/automatic_retraining_parameters.json')


def create_or_update_sink(sink_name: str,
                          destination: str,
                          filter_: str):
    """Creates or updates a sink to export logs to the given Pub/Sub topic.

    The filter determines which logs this sink matches and will be exported
    to the destination.See 
    https://cloud.google.com/logging/docs/view/advanced_filters for more
    filter information.

    Args:
        sink_name: The name of the log sink
        destination: The URI of the pub/sub topic to send the logs to.
        filter_: The log filter for sending logs.
                 Filters only monitoring job anomalies.
    """
    logging_client = logging.Client()
    sink = logging_client.sink(sink_name)

    if sink.exists():
        sink = logging_client.sink(sink_name,
                                   filter_=filter_,
                                   destination=destination)
        sink.update()
        print(f'Updated Anomaly Log Sink {sink.name}.\n')
    else:
        sink = logging_client.sink(sink_name,
                                   filter_=filter_,
                                   destination=destination)
        sink.create()
        print(f'Created Anomaly Log Sink {sink.name}.\n')


def create_or_update_monitoring_job(
    alert_emails: list,
    auto_retraining_params: dict,
    drift_thresholds: dict,
    gs_auto_retraining_params_path: str,
    job_display_name: str,
    log_sink_name: str,
    model_endpoint: str,
    monitoring_interval: int,
    monitoring_location: str,
    project_id: str,
    pubsub_topic_name: str,
    sample_rate: float,
    skew_thresholds: dict,
    target_field: str,
    training_dataset: str):
    """Creates or updates a model monitoring job on the given model.

    Args:
        alert_emails: Optional list of emails to send monitoring alerts.
            Email alerts not used if this value is set to None.
        auto_retraining_params: Pipeline parameter values to use when retraining the model.
            Defaults to None; if left None, the model will not be retrained if an alert is generated.
        drift_thresholds: Compares incoming data to data previously seen to check for drift.
        job_display_name: Display name of the ModelDeploymentMonitoringJob. The name can be up to 128 characters 
            long and can be consist of any UTF-8 characters.
        gs_auto_retraining_params_path: GCS location of the retraining parameters.
        log_sink_name: Name of the log sink object.
        model_endpoint: Endpoint resource name of the deployed model to monitoring.
            Format: projects/{project}/locations/{location}/endpoints/{endpoint}
        monitoring_interval: Configures model monitoring job scheduling interval in hours.
            This defines how often the monitoring jobs are triggered.
        monitoring_location: Location to retrieve ModelDeploymentMonitoringJob from.
        project_id: The project ID.
        pubsub_topic_name: The name of the pubsub topic to publish anomaly logs to (for automatic retraining).
        sample_rate: Used for drift detection, specifies what percent of requests to the endpoint are randomly sampled
            for drift detection analysis. This value most range between (0, 1].
        skew_thresholds: Compares incoming data to the training dataset to check for skew.
        target_field: Prediction target column name in training dataset.
        training_dataset: Training dataset used to train the deployed model. This field is required if
            using skew detection.
    """
    aiplatform.init(project=project_id, location=monitoring_location)

    # check if endpoint exists
    endpoint_list = aiplatform.Endpoint.list(filter=f'endpoint="{model_endpoint.split("/")[-1]}"')
    if not endpoint_list:
        raise ValueError(f'Model endpoint {model_endpoint} not found in {monitoring_location}')
    else:
        endpoint = aiplatform.Endpoint(model_endpoint)

    # Set skew and drift thresholds
    if skew_thresholds:
        skew_config = model_monitoring.SkewDetectionConfig(
            data_source=training_dataset,
            skew_thresholds=skew_thresholds,
            target_field=target_field)
    else:
        skew_config = None

    if drift_thresholds:
        drift_config = model_monitoring.DriftDetectionConfig(
            drift_thresholds=drift_thresholds)
    else:
        drift_config = None

    objective_config = model_monitoring.ObjectiveConfig(
        skew_config, drift_config, explanation_config=None)

    # Create sampling configuration
    random_sampling = model_monitoring.RandomSampleConfig(
        sample_rate=sample_rate)

    # Create schedule configuration
    schedule_config = model_monitoring.ScheduleConfig(
        monitor_interval=monitoring_interval)

    if not alert_emails:
        alert_emails = []

    # Create alerting configuration.
    alerting_config = model_monitoring.EmailAlertConfig(
            user_emails=alert_emails, enable_logging=True)

    # check if job already exists
    job_list = aiplatform.ModelDeploymentMonitoringJob.list(
        filter=f'display_name="{job_display_name}"')
    if not job_list:
        # Create the monitoring job.
        job = aiplatform.ModelDeploymentMonitoringJob.create(
            display_name=job_display_name,
            logging_sampling_strategy=random_sampling,
            schedule_config=schedule_config,
            alert_config=alerting_config,
            objective_configs=objective_config,
            project=project_id,
            location=monitoring_location,
            endpoint=endpoint,
            enable_monitoring_pipeline_logs=True)
    else:
        # Update the monitoring job.
        old_job_id = job_list[0].resource_name.split('/')[-1]
        job = aiplatform.ModelDeploymentMonitoringJob(old_job_id).update(
            display_name=job_display_name,
            logging_sampling_strategy=random_sampling,
            schedule_config=schedule_config,
            alert_config=alerting_config,
            objective_configs=objective_config,
            enable_monitoring_pipeline_logs=True)
        print(f'Updated monitoring job {old_job_id} with new arguments.')

    if auto_retraining_params:
        # Filter to only send anomaly logs to pub/sub
        job_id = job.resource_name.split('/')[-1]
        monitoring_anomaly_log_filter = (
            f'resource.type="aiplatform.googleapis.com/ModelDeploymentMonitoringJob"\n'
            f'resource.labels.location="{monitoring_location}"\n'
            f'resource.labels.model_deployment_monitoring_job="{job_id}"\n'
            f'logName="projects/{project_id}/logs/aiplatform.googleapis.com%2Fmodel_monitoring_anomaly"\n'
            f'severity>=WARNING\n')
        anomaly_log_destination = f'''pubsub.googleapis.com/projects/{project_id}/topics/{pubsub_topic_name}'''
        # Create a log sink to send logs to pub/sub
        create_or_update_sink(
            sink_name=log_sink_name,
            destination=anomaly_log_destination,
            filter_=monitoring_anomaly_log_filter)

        print(f'All anomaly logs for this model monitoring job are being routed to pub/sub topic {pubsub_topic_name} for automatic retraining.')
        print(f'Retraining will use the following parameters located at {gs_auto_retraining_params_path}: \n')
        pp.pprint(auto_retraining_params)

        # Update service account to be able to publish to Pub/Sub
        cloud_logs_sa = 'cloud-logs@system.gserviceaccount.com'
        newline = '\n'
        update_iam = (
            f'''gcloud projects add-iam-policy-binding {project_id} \{newline}'''
            f'''--member="serviceAccount:{cloud_logs_sa}" \{newline}'''
            f'''--role="roles/pubsub.publisher"''')
        print(f'\nUpdating {cloud_logs_sa} with roles/pubsub.publisher')
        execute_process(update_iam, to_null=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str,
                        help='The config file for setting monitoring values.')
    args = parser.parse_args()

    with open(args.config, 'r', encoding='utf-8') as config_file:
        config = yaml.load(config_file, Loader=yaml.FullLoader)

    if config['monitoring']['auto_retraining_params']:
        upload_automatic_retraining_parameters(
            auto_retraining_params=config['monitoring']['auto_retraining_params'],
            gs_auto_retraining_params_path=config['monitoring']['gs_auto_retraining_params_path'],
            gs_pipeline_job_spec_path=config['pipelines']['gs_pipeline_job_spec_path'],
            storage_bucket_name=config['gcp']['storage_bucket_name'])

    create_or_update_monitoring_job(
        alert_emails=config['monitoring']['alert_emails'],
        auto_retraining_params=config['monitoring']['auto_retraining_params'],
        drift_thresholds=config['monitoring']['drift_thresholds'],
        gs_auto_retraining_params_path=config['monitoring']['gs_auto_retraining_params_path'],
        job_display_name=config['monitoring']['job_display_name'],
        log_sink_name=config['monitoring']['log_sink_name'],
        model_endpoint=config['monitoring']['model_endpoint'],
        monitoring_interval=config['monitoring']['monitoring_interval'],
        monitoring_location=config['monitoring']['monitoring_location'],
        project_id=config['gcp']['project_id'],
        pubsub_topic_name=config['gcp']['pubsub_topic_name'],
        sample_rate=config['monitoring']['sample_rate'],
        skew_thresholds=config['monitoring']['skew_thresholds'],
        target_field=config['monitoring']['target_field'],
        training_dataset=config['monitoring']['training_dataset'])
