import boto3
import botocore
import math
import os
import collections
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client('ecs')

def check_for_unbalanced_service(service, min_tasks, max_tasks):

    task_list = ecs.list_tasks(
        cluster=service["clusterArn"],
        serviceName=service["serviceName"]
    )

    task_details = ecs.describe_tasks(
        cluster=service["clusterArn"],
        tasks=task_list["taskArns"]
    )

    containerInstanceArns =[]

    for task in task_details["tasks"]:
        containerInstanceArns.append(task["containerInstanceArn"])

    is_unbalanced = False

    for arn, count in collections.Counter(containerInstanceArns).items():
        if count < min_tasks or count > max_tasks:

            instance_details = ecs.describe_container_instances(
                cluster=service["clusterArn"],
                containerInstances=[arn]
            )

            # Only ACTIVE instances are considered to be unbalanced. 
            # If the instance is already DRAINING, then the tasks on it are already being moved to other instances
            if instance_details["containerInstances"][0]["status"] != "ACTIVE":
                continue
            
            is_unbalanced = True
            if count < min_tasks:
                logger.debug("- Container instance %s has %s tasks running on it, which is lower than the minimum number %s", arn, count, min_tasks)

            if count > max_tasks:
                logger.debug("- Container instance %s has %s tasks running on it, which is higher than the maximum number %s", arn, count, max_tasks)

            break

    return is_unbalanced


# Get list of services running on the cluster, ignoring any DAEMON services (as they only run 1 task per instance)
def get_cluster_services(cluster_name):
    isTruncated = "True"
    nextToken = ""
    all_services = []

    while ("True" == isTruncated):
        if "" == nextToken:
            response = ecs.list_services(
                cluster=cluster_name,
                #schedulingStrategy='REPLICA'   # The current version on the python SDK on lambda seems outdated, and doesn't support this param
            )
        else:
            response = ecs.list_services(
                cluster=cluster_name,
                #schedulingStrategy='REPLICA',   # The current version on the python SDK on lambda seems outdated, and doesn't support this param
                nextToken=nextToken
            )

        if  "nextToken" in response:
            nextToken = response["nextToken"]
        else:
            isTruncated = "False"

        services = response["serviceArns"]
        for service in services:
            all_services.append(service)

    return all_services


def rebalance_service(service):

    logger.info("- Forcing a deployment of service %s to rebalance across instances", service["serviceName"])

    # The AWS refarch example copies and recreates the task def here
    # The problem is that each field has to be defined for a new task def,
    # meaning it's easy for the new task to be missing parts that cause the 
    # new tasks launched from it to fail to start correctly.
    # Instead, just force a new deployment
    response = ecs.update_service(
        cluster=service["clusterArn"],
        service=service["serviceArn"],
        taskDefinition=service["taskDefinition"],
        forceNewDeployment=True
    )

def check_services(total_active_container_instances,service_details):

    for service in service_details["services"]:

        logger.info("Service: %s", service["serviceName"])

        desired_tasks = service["desiredCount"]
        running_tasks = service["runningCount"]

        # Skip any services that don't have any tasks running, as there's nothing to rebalance
        if desired_tasks == 0:
            logger.info("- Skipping this service as the number of desired tasks for the service is set to 0, so nothing to rebalance")
            continue

        # Skip any services that are already doing a deployment
        if len(service["deployments"]) > 1:
            logger.info("- Skipping this service as a deployment is already in progress")
            continue

        # Skip any services that are waiting on tasks to be running
        if running_tasks != desired_tasks:
            logger.info("- Skipping this service as tasks are still starting")
            continue

        rebalance_threshold = round(desired_tasks/total_active_container_instances,2)

        min_tasks_per_instance = math.floor(rebalance_threshold)
        max_tasks_per_instance = math.ceil(rebalance_threshold)

        logger.debug ("- The rebalance threshold for the number of tasks per container instance for this service is: %s", rebalance_threshold)
        logger.debug ("-- The minimum tasks per instance is: %s ", min_tasks_per_instance)
        logger.debug ("-- The maximum tasks per instance is: %s", max_tasks_per_instance)

        if check_for_unbalanced_service(service, min_tasks_per_instance, max_tasks_per_instance):
            rebalance_service(service)
        else:
            logger.info("- This service is already correctly balanced between container instances, so nothing to rebalance")

def lambda_handler(event, context):

    cluster_name = event["cluster_name"]
    logger.info("Starting checking for unbalanced service tasks on cluster '%s'", cluster_name)

    response = ecs.list_container_instances(
        cluster=cluster_name,
        status='ACTIVE'
    )

    total_active_container_instances = len(response["containerInstanceArns"])

    cluster_services = get_cluster_services(cluster_name)

    for i in range(0, len(cluster_services), 10):
        service_details = ecs.describe_services(
            cluster=cluster_name,
            services=cluster_services[i:i + 10]
        )

        check_services(total_active_container_instances,service_details)
            
    logger.info("Finished checking for unbalanced service tasks on cluster '%s'", cluster_name)
