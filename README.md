# CloudWatch

Retrieve data about your EC2 Instances using AWS Cloud Watch.

This block will start by querying AWS to determine which instances can capture the metric specified with the block. It will cache those instances internally - so if you add an instance and want to track it, you will need to restart the service.

It will then, for each call to `process_signals`, make one request per instance to try to gather the data for the metric that the block has been configured with. If data exists, it will store the result of the metric using the method provided in **statistic** in a field called `value`.

Once all instances have been queried, a list of the valid output signals will be notified.


## Properties

 - **AWS Region**: The AWS region to connect to
 - **Access Key**: An AWS Access Token
 - **Access Secret**: The AWS Access Token's secret
 - **Metric to Monitor**: (string) Which metric you want to monitor - [Possible Metrics](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/ec2-metricscollected.html)
 - **Lookback Minutes**: (int) How many minutes to look back for data. Only the latest data point will be output
 - **Result Period Minutes**: (int) How many minutes the period of the data should represent. Tweak this to get the last hour's average CPU for example.
 - **Statistic**: How do you want to consolidate the data points


## Dependencies

 * boto - https://github.com/boto/boto

## Commands

None

TODO: Add command to re-sync the instance IDs

## Input

Any signal(s).

Note: only one request set will be made per list of signals processed. A request set is comprised of one request per instance

## Output

One signal per instance. The signal will have the following format:

```python
 {
   'instance_id': '<The string instance ID of the instance in question>',
   'value': '<The result of the calculation>'
 }
```
