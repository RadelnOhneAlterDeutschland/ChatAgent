Feature: Multi-user access to the chat agent
  As a person with documents to ask questions about
  I want my own account
  So that my documents and conversations stay separate from everyone else's

  Scenario: A new person registers an account
    Given no one has registered with "ana@example.com"
    When she registers with "ana@example.com" and password "correct-horse-battery"
    Then her account exists
    And she is not told her own password back

  Scenario: An email address can only be registered once
    Given a registered user "ana@example.com" with password "correct-horse-battery"
    When someone else tries to register with "ana@example.com" and password "another-password"
    Then the registration is refused as already taken

  Scenario Outline: Registration refuses credentials that are unusable
    Given no one has registered with "<email>"
    When she registers with "<email>" and password "<password>"
    Then the registration is refused as invalid

    Examples:
      | email             | password             |
      | not-an-email      | correct-horse-battery |
      | ana@example.com   | short                |

  Scenario: A registered user signs in
    Given a registered user "ana@example.com" with password "correct-horse-battery"
    When she signs in with password "correct-horse-battery"
    Then she receives an access token

  Scenario: Signing in with the wrong password is refused
    Given a registered user "ana@example.com" with password "correct-horse-battery"
    When she signs in with password "guessing-wildly"
    Then she is refused access

  Scenario: Signing in as an unknown user is refused
    Given no one has registered with "ghost@example.com"
    When "ghost@example.com" signs in with password "correct-horse-battery"
    Then she is refused access

  Scenario: A signed-in user can see who she is
    Given a signed-in user "ana@example.com"
    When she asks who she is
    Then she is told her email is "ana@example.com"

  Scenario: An anonymous visitor cannot see account details
    Given a visitor who has not signed in
    When she asks who she is
    Then she is refused access

  Scenario: A tampered token does not grant access
    Given a signed-in user "ana@example.com"
    When she asks who she is using a tampered token
    Then she is refused access

  Scenario: An expired token does not grant access
    Given a signed-in user "ana@example.com" whose token has expired
    When she asks who she is
    Then she is refused access
