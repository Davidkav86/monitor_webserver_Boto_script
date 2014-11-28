#!/usr/bin/python -tt

import sys
import commands
import time
import boto.ec2
import boto.ec2.cloudwatch
import boto.ec2.autoscale
import boto.sns
import datetime
from boto.ec2.autoscale import LaunchConfiguration
from boto.ec2.autoscale import AutoScalingGroup
from boto.ec2.autoscale import ScalingPolicy
from boto.ec2.autoscale import Tag

# Boolean used to ensure the alarm is only placed on an instance once
alarmed = False
# Global variable for the instance
instance = None

#
# Uses the get_all_instances method to connect to a instance that has already been created.
# Checks if the instance is running, starts it if not. Uses a while loop to show the user
# the basic menu options
#
def start(instance_id):
	global instance
	conn = boto.ec2.connect_to_region('eu-west-1')
	instanceids = [instance_id]
	reservation_list = conn.get_all_instances(instance_ids = instanceids)
	reservation = reservation_list[0]
	instance_list = reservation.instances
	instance = instance_list[0]
	menu = {'1' : 'Create a Cloudwatch alarm', '2' : 'Monitor Instance','3' : 'Trigger Alarm', '0' : 'Exit'}

	if instance.state != 'running':
		instance.start
		print 'Instance is starting..'
		while instance.state != 'running':
			import time
			time.sleep(5)
			instance.update
		print '\nInstance started'

	exit = False
	while exit != True:
		options = menu.keys()
		options.sort()
		for entry in options:
			print entry, menu[entry]


		input = raw_input('Input: ')
		if input == '1':
			create_alarm(instance_id)
		elif input == '2':
			monitor_instance(instance_id)
		elif input == '3':
			trigger_alarm()
		elif input == '0':
			exit = True
			break
        else:
        	print '\nInvalid Input\n'


# 
# Creates a new cloudwatch alarm based on incomming network traffic.  The boto simple notification 
# service (sns) APi is used to create a topic and a subscription so notification can take place 
# if the alarm is triggered. 
#
def create_alarm(instance_id):
	global alarmed
	if alarmed == False:
	    sns = boto.sns.connect_to_region('eu-west-1')
	    sns.create_topic('DavidK_Network_Problem') # Create a topic
	    arn = 'arn:aws:sns:eu-west-1:808146113457:DavidK_Network_Problem' #Amazon Resource Name, uniquely identify AWS resources
	    sns.subscribe(arn, "email", "david_kav@hotmail.com") # subscribe my email to the topic

	    cloudwatch = boto.ec2.cloudwatch.connect_to_region('eu-west-1')
	    # create a list holding the metric that the alarm will be based on
	    metrics = cloudwatch.list_metrics(dimensions={'InstanceId' : instance_id},metric_name='NetworkIn')
	    # call to create the autoscaling group and to get policy arn for the alarm
	    as_policy_arn = create_auto_scaling(instance_id)
	    # create the alarm
	    alarm = metrics[0].create_alarm(name='Network_Usage_Alarm', comparison='>=', threshold=500000, period=60,
                    evaluation_periods=1, statistic='Average', alarm_actions=[arn,as_policy_arn])
	    if alarm:
	    	print '\n----------'
		    print 'Alarm set'
		    print '----------\n'
		    alarmed = True
	    else:
		    print '\nAlarm has not been set\n'
	else:
		print 'An alarm has already been set on this instance'

#
# Create a launch configuration using the AMI created in the tutorial. An autoscaling group is then created using the
# launch config. A scaling policy is created and associated with the AS group. The ARN is returned so the autoscaling
# group can be added to the cloudwatch alarm
#
def create_auto_scaling(instance_id):
	autoscaling_conn = boto.ec2.autoscale.connect_to_region('eu-west-1')
	# Create launch configuration using my ami from the tutorial
	launch_config = LaunchConfiguration(name = 'DK-LC-Boto', image_id = 'ami-86c87ef1', instance_type = 't2.micro',
		key_name = 'David_kav', security_groups = ['witsshrdp'])
	autoscaling_conn.create_launch_configuration(launch_config)
    
    # create an autoscaling group
	autoscaling_group = AutoScalingGroup(name = 'DK-AutoScale-Boto',
		launch_config = launch_config,
		min_size = 1, max_size = 3,
		availability_zones = ['eu-west-1a', 'eu-west-1b'],
		# vpc_zone_identifier = ['subnet-747ea503','subnet-bfcb34e6'],
		# security_group_ids = ['sg-0edd5d6b'], 
		connection = autoscaling_conn)
    
    # tag the instance
	tag = Tag(propagate_at_launch = True, resource_id = 'DK-AutoScale-Boto')
	tag.key = 'Name'
	tag.value = "P_DavidK_boto"
	tags_list = [tag]
	autoscaling_group.tags = tags_list
	# submit the group to aws
	autoscaling_conn.create_auto_scaling_group(autoscaling_group)

    # create a scaling policy
	scale_up_policy = ScalingPolicy(name = 'scale_up',adjustment_type = 'ChangeInCapacity',
		as_name = 'DK-AutoScale-Boto',scaling_adjustment = 1, cooldown = 180)
    # submit the policy to aws through the autoscaling connection object
	autoscaling_conn.create_scaling_policy(scale_up_policy)
    # get the policy now that aws has added the extra properties
	scale_up_policy = autoscaling_conn.get_all_policies(as_group='DK-AutoScale-Boto', policy_names=['scale_up'])[0]

	as_policy_arn = scale_up_policy.policy_arn

	return as_policy_arn



#
# Allows the user to monitor a list of metrics. A cloudwactch object is initialised
# The cloudwatch object is used to get the statistics for a metric chosen by the user
# by passing it into the get_metric_statistics method. 
#
def monitor_instance(instance_id):
	metrics = {'0' : 'Exit', '1' : 'CPUUtilization', '2' : 'NetworkIn', '3' : 'NetworkOut', '4' : 'DiskReadOps', '5' : 'DiskWriteOps'}
	descriptions = {'CPUUtilization' : 'The percentage of allocated EC2 compute units that are currently in use on the instance',
	              'NetworkIn':'This metric identifies the volume of incoming network traffic to an application on a single instance',
	              'NetworkOut':'This metric identifies the volume of outgoing network traffic to an application on a single instance',
	              'DiskReadOps':'Completed read operations from all ephemeral disks available to the instance in a specified period of time',
	              'DiskWriteOps':'Completed write operations to all ephemeral disks available to the instance in a specified period of time'}
	
	options = metrics.keys()
	options.sort()
	print '\nChoose a metric to monitor:'
	for entry in options:
		print entry, metrics[entry]
	input = raw_input('Input: ')

	if input in options:
	    metric = metrics[input]

	    cloudwatch = boto.ec2.cloudwatch.connect_to_region('eu-west-1')
	    stats = cloudwatch.get_metric_statistics(300,
	   	    datetime.datetime.utcnow() - datetime.timedelta(seconds=600),
	   	    datetime.datetime.utcnow(),
	   	    metric,
    	    'AWS/EC2',
    	    'Average',
    	    dimensions={'InstanceId' : instance_id})

	    if stats:
		    statistics = stats[0]
		    print '\n', metric + ' ::'
		    print descriptions[metric]
		    print '--------------------------'
		    for x,y in statistics.iteritems():
			    print x +' : ', y
		    print '--------------------------'
	else:
		print '\nInvalid option\n'

#
# Uses a loop to send repeated curl requests to the url of the instance. This will cause the stated threshold 
# to be passed and therefor trigger the cloudwatch alarm which creates a new instance
#
def trigger_alarm():
	global alarmed
	global instance

	dns = instance.public_dns_name
	url = '"http://' + dns + '"'
	if alarmed == True:
	    
	    i = 0
	    cmd = 'curl ' + url
	    print '\nRunning script to trigger alarm\n'
	    while i < 1000:
	    	commands.getstatusoutput(cmd)
	    	i = i + 1

	else:
		print '\nNo alarm has been set'
		print 'Set a CloudWatch alarm first\n'



def main():
	print'  --------------- Monitor Webserver ------------------- \n'
	print'Enter the Instance Id of the Instance you wish to connect to'
	input = raw_input('Input: ')

	if input == '1':
		input = 'i-dc65923a'


	start(input)


if __name__ == '__main__':
    main()