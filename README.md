CloudWatch
==========
Retrieve data about your AWS resources using AWS Cloud Watch.  

This block will start by querying AWS to determine which metrics can capture the metric specified with the block. It will cache those metric objects internally - so if you add an instance and want to track it, you will need to restart the service.

It will then, for each call to `process_signals`, make one request per metric to try to gather the data for the metric that the block has been configured with. If data exists, it will store the result of the metric using the method provided in **statistic** in a field called `value`.

Once all metrics have been queried, a list of the valid output signals will be notified.

Properties
----------
- **creds**: Credentials to log into and sync with AWS account
- **lookback_mins**: How many minutes to look back for data. Only the latest data point will be output.
- **metric**: Which metric you want to monitor - [Example EC2 Metrics](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/ec2-metricscollected.html).
- **result_period**: How many minutes the period of the data should represent. Tweak this to get the last hour's average CPU for example.
- **statistic**: How do you want to consolidate the data points.

Inputs
------
- **default**: Any list of signals.  Only one request set will be made per list of signals processed.  A request set is comprised of one request per metric.

Outputs
-------
- **default**: One signal per metric.  See example below for details.

Commands
--------
None

Dependencies
------------
 * boto - https://github.com/boto/boto

Output Example
--------------
One signal per metric. The signal will have the following format:
```python
 {
   'dimensions': '<The Dimension object containing the dimensions of the metric>',
   'value': '<The result of the calculation>'
 }
```
Here is an example of what a dimension of an EC2 CloudWatch Metric would look like. Note the instance ID is in a list of one element.
```python
{
  'InstanceId': ['i-XXXXXXX']
}
```

