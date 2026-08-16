Feature: Chatting with the agent about my documents
  As a signed-in user
  I want to ask questions in natural language
  So that I get an answer grounded in the shared document library, with a citation I can check

  Background:
    Given a signed-in user "ana@example.com"

  Scenario: A question grounded in a shared document gets a cited answer
    Given "revenue.pdf" containing "The quarterly revenue was four point two million dollars" is in the shared library
    And the assistant will look up "quarterly revenue" and reply "Quarterly revenue was $4.2 million [revenue.pdf p.1]."
    When she asks "What was the quarterly revenue?"
    Then she receives the answer "Quarterly revenue was $4.2 million [revenue.pdf p.1]."
    And the answer cites page 1 of "revenue.pdf"

  Scenario: A question needing no document lookup still gets answered
    Given the assistant will reply directly "I'm doing well, thank you!"
    When she asks "How are you?"
    Then she receives the answer "I'm doing well, thank you!"
    And the answer has no citations

  Scenario: The conversation remembers earlier turns in the same session
    Given the assistant will reply directly "Nice to meet you, Ana."
    And she asked "My name is Ana." and started a session
    And the assistant will reply directly "Your name is Ana."
    When she asks "What's my name?" in the same session
    Then she receives the answer "Your name is Ana."
    And the assistant was shown her earlier message as history

  Scenario: She can see her past sessions
    Given the assistant will reply directly "I'm doing well, thank you!"
    And she asked "How are you?" and started a session
    When she lists her chat sessions
    Then a session titled "How are you?" is among them

  Scenario: One person's chat sessions are invisible to another
    Given another registered user "bob@example.com" asked "Secret question" and started a session
    When she lists her chat sessions
    Then she has no chat sessions

  Scenario: An anonymous visitor cannot chat
    Given a visitor who has not signed in
    When she asks "What was the quarterly revenue?"
    Then the request is refused as unauthorised
