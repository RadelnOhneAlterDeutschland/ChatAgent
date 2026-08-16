Feature: A shared library of documents, kept in sync from a watched folder
  As someone who dropped PDFs into a shared folder
  I want the agent to notice and index them automatically
  So that any signed-in user can ask questions about them, without anyone uploading anything by hand

  Background:
    Given a signed-in user "ana@example.com"

  Scenario: A PDF placed in the watched folder becomes searchable
    Given a PDF named "revenue.pdf" containing "The quarterly revenue was four point two million dollars" sits in the watched folder
    When the folder-sync job runs
    Then "revenue.pdf" is ready in the shared library
    And searching for "quarterly revenue" finds page 1 of "revenue.pdf"

  Scenario: A scanned PDF is read by optical character recognition
    Given the scanning service can read "Handwritten note about the merger timeline" from page 1
    And a scanned PDF named "scan.pdf" sits in the watched folder
    When the folder-sync job runs
    Then "scan.pdf" is ready in the shared library
    And searching for "merger timeline" finds page 1 of "scan.pdf"

  Scenario: A file that cannot be read is reported as failed, not silently lost
    Given a file named "corrupt.pdf" that is not really a PDF sits in the watched folder
    When the folder-sync job runs
    Then "corrupt.pdf" is listed as failed in the shared library

  Scenario: Re-running the sync on an unchanged file does not duplicate it
    Given a PDF named "revenue.pdf" containing "The quarterly revenue was four point two million dollars" sits in the watched folder
    And the folder-sync job has already run once
    When the folder-sync job runs
    Then "revenue.pdf" appears exactly once in the shared library

  Scenario: A modified file in the watched folder is re-ingested
    Given a PDF named "revenue.pdf" containing "Old figures from last quarter" sits in the watched folder
    And the folder-sync job has already run once
    When the file "revenue.pdf" in the watched folder is replaced with a PDF containing "New figures about a merger this quarter"
    And the folder-sync job runs
    Then searching for "merger" finds page 1 of "revenue.pdf"

  Scenario: Every signed-in user sees the same shared library
    Given a PDF named "revenue.pdf" containing "The quarterly revenue was four point two million dollars" sits in the watched folder
    And the folder-sync job runs
    And another registered user "bob@example.com" signs in
    When Bob lists the shared documents
    Then "revenue.pdf" is among them

  Scenario: Every signed-in user can search the same shared library
    Given a PDF named "revenue.pdf" containing "The quarterly revenue was four point two million dollars" sits in the watched folder
    And the folder-sync job runs
    And another registered user "bob@example.com" signs in
    When Bob searches for "quarterly revenue"
    Then Bob finds page 1 of "revenue.pdf"

  Scenario: Deleting a document removes it from search
    Given a PDF named "revenue.pdf" containing "The quarterly revenue was four point two million dollars" sits in the watched folder
    And the folder-sync job runs
    When she deletes "revenue.pdf"
    Then "revenue.pdf" is no longer among the shared documents
    And searching for "quarterly revenue" finds nothing

  Scenario: An anonymous visitor cannot see the shared library
    Given a visitor who has not signed in
    When she lists the shared documents
    Then the request is refused as unauthorised
