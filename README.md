# ECS-Service-Rebalancer
Provides rebalancing for ECS Service Tasks using a scheduled CloudWatch Event and Lambda, similar to the AWS sample [ecs-refarch-task-rebalancing](https://github.com/aws-samples/ecs-refarch-task-rebalancing)


## Intro (taken from the AWS Sample)

> Consider an ECS cluster with tasks distributed evenly across multiple ECS instances within the cluster. If the cluster is scaled down in order to save cost, the tasks on the removed instance are assigned to remaining nodes automatically. However, when the ECS cluster is scaled up again, tasks are not automatically redistributed across all available instances. This leads to unused capacity and an under-utilized cluster, which could negatively affect application availibility.

## Why not just use the AWS Sample?

The AWS Sample is a good starting point, but there's a few things that can be improved:

AWS Sample | ECS-Service-Rebalancer
-----|------
Redeploys all Services | Checks to see if a Service is unbalanced across instances to avoid unnecessary deployments
Creates a new Task Definition | Uses the `forceNewDeployment` parameter instead, which is less error prone than replacing the Task Definition
|| Only counts `ACTIVE` instances as being available and part of the cluster 
|| Checks if unbalanced instances are already `DRAINING`, to avoid a deployment if Tasks are already being moved
|| Ignores any Services that have a `Desired Task Count = 0`
|| Ignores any Services where a deployment is already in progress
|| Ignores any Services where Tasks are still being started or stopped (e.g. `Running Task Count != Desired Task Count`)
|| Uses a upper and lower threshold per Service to decide whether an instance is unbalanced
