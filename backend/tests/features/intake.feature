Feature: Smart intake — filing a new document with the author's confirmation
  As the author of a new document
  I want the app to suggest where it belongs in the existing folder taxonomy
  So that I can file it correctly without doing the classification myself, while staying in control of the final placement

  Background:
    Given a signed-in user "ana@example.com"
    And the topic folders "05 Finanzierung" and "09 Rechtliches" already exist
    And "05 Finanzierung" already has the subfolder "Foerderantraege"

  Scenario: Submitting a document returns a folder suggestion, nothing filed yet
    Given the classifier will suggest topic "05 Finanzierung", subfolder "Foerderantraege", because "It's a grant application."
    When she submits "grant.pdf" containing "This is a grant application for a rikscha" for placement
    Then she is offered "05 Finanzierung" / "Foerderantraege" as the suggested placement
    And "grant.pdf" is not yet in the shared library
    And "grant.pdf" is not yet filed anywhere on disk

  Scenario: Accepting the suggestion files the document where it was suggested
    Given the classifier will suggest topic "05 Finanzierung", subfolder "Foerderantraege", because "It's a grant application."
    And she submitted "grant.pdf" containing "This is a grant application for a rikscha" for placement
    When she confirms the suggested placement
    Then "grant.pdf" is ready in the shared library
    And "grant.pdf" is filed under "05 Finanzierung/Foerderantraege"

  Scenario: The author can override the suggestion with a different existing topic
    Given the classifier will suggest topic "05 Finanzierung", subfolder "Foerderantraege", because "It's a grant application."
    And she submitted "grant.pdf" containing "This is a grant application for a rikscha" for placement
    When she confirms placement under "09 Rechtliches" instead
    Then "grant.pdf" is ready in the shared library
    And "grant.pdf" is filed under "09 Rechtliches"

  Scenario: The author can file into a brand-new subfolder under an existing topic
    Given the classifier will suggest topic "05 Finanzierung", subfolder "Foerderantraege", because "It's a grant application."
    And she submitted "grant.pdf" containing "This is a grant application for a rikscha" for placement
    When she confirms placement under "05 Finanzierung" with new subfolder "Rikscha-Foerderung"
    Then "grant.pdf" is ready in the shared library
    And "grant.pdf" is filed under "05 Finanzierung/Rikscha-Foerderung"

  Scenario: An anonymous visitor cannot submit a document for placement
    Given a visitor who has not signed in
    When she submits "grant.pdf" containing "irrelevant text" for placement
    Then the request is refused as unauthorised
