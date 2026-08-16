Feature: Service availability
  As an operator
  I want to confirm the service is running
  So that deployments and load balancers can tell healthy instances from broken ones

  Scenario: A running service reports itself healthy
    Given the service is running
    When an operator checks the service health
    Then the service reports that it is healthy

  Scenario: A running service reports which release it is running
    Given the service is running
    When an operator checks the service health
    Then the service reports its version
