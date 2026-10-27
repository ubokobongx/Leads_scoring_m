"""SQL builders. Pure functions — no I/O."""

def id_digits() -> str:
    return """REGEXP_REPLACE(COALESCE(
      CASE WHEN phone_number IS NOT NULL AND phone_number !~ '[^0-9]' THEN phone_number END,
      CASE WHEN distinct_id  IS NOT NULL AND distinct_id  !~ '[^0-9]' THEN distinct_id  END,
      CASE WHEN user_id      IS NOT NULL AND user_id      !~ '[^0-9]' THEN user_id      END
    ), '[^0-9]', '')"""


def std_phone_sql(col: str) -> str:
    return f"""CASE
      WHEN LEN({col}) = 0 THEN NULL
      WHEN {col} LIKE '234%' THEN LEFT({col}, 13)
      WHEN {col} LIKE '0%'   THEN '234' || SUBSTRING({col}, 2, 10)
      WHEN LEN({col}) = 10   THEN '234' || {col}
      WHEN LEN({col}) > 10   THEN '234' || LEFT({col}, 10)
      WHEN LEN({col}) >= 9   THEN {col}
      ELSE NULL END"""


def events_sql(min_h: int, max_h: int) -> str:
    return f"""
WITH src AS (
  SELECT {id_digits()} AS d, LOWER(event) AS event, CAST(created_at AS TIMESTAMP) AS event_timestamp,
         display_name
  FROM "ox_datawarehouse"."mixpanel"."mp_events"
  WHERE created_at >= DATEADD(hour, -{max_h}, GETDATE())
    AND created_at <  DATEADD(hour, -{min_h}, GETDATE())
)
SELECT
  {std_phone_sql('d')} AS phone_number,
  event, event_timestamp, display_name,
  CASE WHEN event LIKE 'investment%' OR event LIKE '%_investment' OR event LIKE 'check_investment%' THEN 1 ELSE 0 END AS is_investment_event,
  CASE WHEN event LIKE 'loan%'       OR event LIKE '%_loan'       THEN 1 ELSE 0 END AS is_loan_event,
  CASE
    WHEN event LIKE 'investment%' OR event LIKE '%_investment' OR event LIKE 'check_investment%' THEN
      CASE
        WHEN event IN (
          'investment_get_all_started','investment_get_all_successful','investment_get_all_failed',
          'investment_product_details_started','investment_product_details_successful','investment_product_details_failed',
          'investment_referral_history_all_started','investment_referral_history_all_successful','investment_referral_history_all_failed',
          'investment_referral_summary_performance_all_started','investment_referral_summary_performance_all_successful',
          'investment_referral_summary_performance_all_failed') THEN 1
        WHEN event IN (
          'investment__product_option_started','investment__product_option_successful','investment__product_option_failed',
          'investment_product_option_started','investment_product_option_successful','investment_product_option_failed',
          'investment__single_details_started','investment__single_details_successful','investment__single_details_failed') THEN 3
        WHEN event IN (
          'investment_validate_address_started','investment_validate_address_successful_awaiting_approval',
          'investment_validate_address_failed_not_submitted_for_approval') THEN 10
        WHEN event IN (
          'investment_create_started','investment_create_successful','investment_create_failed',
          'check_investment_card_funding_started','check_investment_funding_card_failed',
          'check_investment_funding_transfer_pending','check_investment_transfer_funding_started',
          'check_investment_funding_transfer_failed',
          'investment_validate_pin_started','investment_validate_pin_successful','investment_validate_pin_failed',
          'investment_liquidate_started','investment_liquidate_successful','investment_liquidate_failed') THEN 12
        WHEN event IN (
          'onboarding_proceed_add_bank_started_investment','onboarding_proceed_add_bank_successful_investment',
          'onboarding_proceed_add_bank_failed_investment') THEN 8
        ELSE 0
      END

    WHEN event IN (
      '$identify','$ae_session','$ae_first_open','$ae_updated','$ae_crashed',
      'tap_sign_up','onboarding_select_individual_user','onboarding_select_corporate_user',
      'onboarding_create_user_started','onboarding_create_user_successful','onboarding_create_user_failed',
      'onboarding_otp_verified_started','onboarding_otp_verified_successful','onboarding_otp_verified_failed',
      'login_start','login_failed','login_successful',
      'get_user_details_start','get_user_details_successful','get_user_details_failed',
      'get_kyc_start','get_kyc_successful','get_kyc_failed',
      'faq_get_faqs_list_started','faq_get_faqs_list_successful',
      'faq_get_faqs_list_failed','faq_get_faqs_list_failure',
      'test-user-created') THEN 1

    WHEN event IN (
      'onboarding_create_password_started','onboarding_create_password_successful','onboarding_create_password_failed') THEN 2

    WHEN event IN (
      'onboarding_create_security_question_started','onboarding_create_security_question_successful',
      'onboarding_create_security_question_failed') THEN 3

    WHEN event IN (
      'onboarding_proceed_with_bvn_started','onboarding_proceed_with_bvn_successful','onboarding_proceed_with_bvn_failed',
      'kyc_proceed_with_bvn_started','kyc_proceed_with_bvn_successful','kyc_proceed_with_bvn_failed') THEN 4

    WHEN event IN (
      'onboarding_proceed_get_selfie_provider_started','onboarding_proceed_get_selfie_provider_successful',
      'onboarding_proceed_get_selfie_provider_failed','onboarding_proceed_take_a_selfie_started',
      'onboarding_proceed_take_a_selfie_successful','onboarding_proceed_take_a_selfie_failed',
      'onboarding_proceed_take_a_selfie_max_retry_reached','kyc_proceed_get_selfie_provider_started',
      'kyc_proceed_get_selfie_provider_successful','kyc_proceed_get_selfie_provider_failed',
      'kyc_proceed_take_a_selfie_started','selfie_verification_successful','selfie_verification_failed',
      'onboarding_get_smileid_user_properties_started','onboarding_get_smileid_user_properties_successful',
      'onboarding_get_smileid_user_properties_failed',
      'onboarding_get_smileid_user_properties_forwebcomponent_started',
      'onboarding_get_smileid_user_properties_forwebcomponent_successful',
      'onboarding_proceed_submit_selfie_compare_started',
      'onboarding_proceed_submit_selfie_compare_successful',
      'onboarding_proceed_submit_selfie_compare_failed') THEN 5

    WHEN event IN (
      'loan_update_profile_nok_started','loan_update_profile_nok_successful','loan_update_profile_nok_failed',
      'loan_validate_nin_started','loan_validate_nin_successful','loan_validate_nin_failed') THEN 6

    WHEN event IN (
      'onboarding_proceed_add_employment_details_started','onboarding_proceed_add_employment_details_successful',
      'onboarding_proceed_add_employment_details_failed','kyc_proceed_add_employment_details_started',
      'kyc_proceed_add_employment_details_successful','kyc_proceed_pep_status_started',
      'loan_update_pep_status_started','loan_update_pep_status_successful','loan_update_pep_status_failed',
      'profile_pep_update_started','profile_pep_update_successful',
      'profile_start_employment_details_flow') THEN 7

    WHEN event IN (
      'profile_bank_select_bank','profile_personal_info_tap','profile_personal_info_fill_form2',
      'profile_tap',
      'onboarding_proceed_add_bank_started','onboarding_proceed_add_bank_successful','onboarding_proceed_add_bank_failed',
      'onboarding_proceed_add_bank_started_loan','onboarding_proceed_add_bank_successful_loan',
      'onboarding_proceed_add_bank_failed_loan',
      'kyc_proceed_add_bank_started','kyc_proceed_add_bank_successful','kyc_proceed_add_bank_failed',
      'onboarding_proceed_create_pin_started','onboarding_proceed_create_pin_successful','onboarding_proceed_create_pin_failed',
      'onboarding_create_pin',
      'kyc_proceed_create_pin_started','kyc_proceed_create_pin_failed',
      'profile_kin_details_tap','profile_kin_details_tap_first_name','profile_kin_details_tap_last_name') THEN 8

    WHEN event IN (
      'loans_begin','loans_top_up_select_loan_amount',
      'loan_creation_started','loan_creation_successful','loan_creation_failed',
      'loans_ineligible') THEN 9

    WHEN event IN (
      'loan_update_physical_started','loan_update_physical_successful','loan_update_physical_failed',
      'loan_validate_address_started','loan_validate_address_successful_awaiting_approval',
      'loan_validate_address_successful','loan_validate_address_failed_not_submitted_for_approval',
      'loan_validate_address_failed',
      'officer_address_verification_rejected','officer_address_verification_approved',
      'supervisor_address_verification_rejected','supervisor_address_verification_approved',
      'loan_setup_repayment_started','loan_setup_repayment_successful','loan_setup_repayment_failed',
      'loan_setup_repayment_pending_verification',
      'loan_update_profile_marital_status_started','loan_update_profile_marital_status_successful',
      'configuration_fetch_card_tokenize_direct_debit_started',
      'configuration_fetch_card_tokenize_direct_debit_successful',
      'configuration_fetch_card_tokenize_direct_debit_failed') THEN 10

    WHEN event IN (
      'loan_approval_started','loan_approval_successful','loan_approval_failed',
      'loan_get_offer_letter_started','loan_get_offer_letter_successful','loan_get_offer_letter_failed',
      'loans_view_offer_letter','loans_accept_terms','loans_pin_validation_failed',
      'loan_decline_loan_started','loan_decline_loan_successful','loan_decline_loan_failed',
      'loan_decline_started','loan_decline_successful','loan_decline_failed',
      'loan_cancelation_started','loan_cancelation_successful','loan_cancelation_failed',
      'loan_cancellation_started','loan_cancellation_successful','loan_cancellation_failed') THEN 11

    WHEN event IN (
      'loan_validate_pin_started','loan_validate_pin_successful','loan_validate_pin_failed',
      'loan_disbursal_started','loan_disbursal_successful','loan_disbursal_failed',
      'loans_taken_successfully','loans_user_rate',
      'transfer_transfer_status_check_started','transfer_transfer_status_check_successful',
      'transfer_transfer_status_check_failed',
      'transfer_save_receipt',
      'transfer_get_reciept_started','transfer_get_reciept_successful','transfer_get_reciept_failed',
      'loans_liquidate_pay_via_transfer_copy_account_number',
      'transaction_statement_get_statement_started',
      'transaction_statement_get_statement_successful',
      'transaction_statement_get_statement_failed',
      'change_pin_started','change_pin_successful','change_pin_failed',
      'change_pin_get_otp_successful','change_pin_get_otp_failed',
      'change_password_started','change_password_successful','change_password_failed',
      'change_password_get_otp_successful','change_password_get_otp_failed',
      'wallet_withdrawal_started','wallet_withdrawal_validate_pin_started',
      'wallet_withdrawal_validate_pin_successful','wallet_withdrawal_validate_pin_failed',
      'wallet_withdrawal_failed',
      'get_user_bank_accounts_started','get_user_bank_accounts_successful') THEN 12

    ELSE 0
  END AS stage_number
FROM src
WHERE d IS NOT NULL AND d <> ''
"""


def journey_sql(phone_list: str, use_window: bool, max_h: int) -> str:
    window_clause = (
        f"    AND created_at >= DATEADD(hour, -{max_h}, GETDATE())\n"
        f"    AND created_at <  GETDATE()\n"
        if use_window else ""
    )
    return f"""
SELECT * FROM (
  SELECT {std_phone_sql("REGEXP_REPLACE(phone_number, '[^0-9]', '')")} AS phone_number,
         CAST(created_at AS TIMESTAMP) AS created_at,
         channels,
         full_name,
         UPPER(TRIM(decision_state))      AS decision_state,
         UPPER(TRIM(current_loan_status)) AS current_loan_status,
         ROW_NUMBER() OVER (PARTITION BY REGEXP_REPLACE(phone_number,'[^0-9]','') ORDER BY created_at DESC) AS rn
  FROM "ox_datawarehouse"."oxygenx"."customer_journey"
  WHERE phone_number IS NOT NULL
    AND REGEXP_REPLACE(phone_number, '[^0-9]', '') IN ({phone_list})
{window_clause}) t
WHERE rn = 1 AND phone_number IS NOT NULL
"""


def lookback_sql(table: str, days: int) -> str:
    return f"""
SELECT DISTINCT phone_number, status, knock_off_reason
FROM {table}
WHERE base_date >= DATEADD(day, -{days}, CURRENT_DATE)
  AND base_date <  CURRENT_DATE
"""