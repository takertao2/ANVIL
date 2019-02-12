import logging, argparse, sys, json, time, os, random

from ctypes import CDLL

from sovrin_utilities import run_coroutine, send_data, receive_data

from setup import setup_pool, setup_steward, teardown
from onboarding import simple_onboard, onboard_for_proving, onboarding
from credentials import create_schema, create_credential_definition
from issue import offer_credential, receive_credential_offer, request_credential, create_and_send_credential, store_credential
from proofs import request_proof_of_credential, create_proof_of_credential, verify_proof

from sovrin_utilities import read_json


from indy import wallet, did
from indy.error import IndyError, ErrorCode

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARN)

parser = argparse.ArgumentParser(description='Run python getting-started scenario (Prover/Issuer)')
parser.add_argument('-t', '--storage_type', help='load custom wallet storage plug-in')
parser.add_argument('-l', '--library', help='dynamic library to load for plug-in')
parser.add_argument('-e', '--entrypoint', help='entry point for dynamic library')
parser.add_argument('-c', '--config', help='entry point for dynamic library')
parser.add_argument('-s', '--creds', help='entry point for dynamic library')

args = parser.parse_args()


# Check if we need to dyna-load a custom wallet storage plug-in
if args.storage_type:
    if not (args.library and args.entrypoint):
        parser.print_help()
        sys.exit(0)
    stg_lib = CDLL(args.library)
    result = stg_lib[args.entrypoint]()
    if result != 0:
        print('Error unable to load wallet storage', result)
        parser.print_help()
        sys.exit(0)

    print('Success, loaded wallet storage', args.storage_type)


async def run():

    cred_request, schema, proof_request, assertions_to_make, self_attested_attributes, \
    requested_attributes, requested_predicates, non_issuer_attributes \
    = load_example_data('../example_data/service_example/')

    # Add a nonce to the proof request and stringify
    proof_request['nonce'] = ''.join(random.choice('0123456789') for i in range(25))

    # Requests need to be json formatted
    proof_request = json.dumps(proof_request)
    cred_request = json.dumps(cred_request)

    # Set up actors - LOAD KEYS AS ENVIRONMENT VARIABLES
    pool_name, pool_handle = await setup_pool('ANVIL')
    steward = await setup_actor('Steward', 'mocked_steward_id', 'mocked_steward_key', '000000000000000000000000Steward1', pool_handle)
    issuer = await setup_actor('Issuer', 'mocked_issuer_id', 'mocked_issuer_key', '000000000000000000000000Issuer01', pool_handle)
    prover = await setup_actor('Prover', 'mocked_prover_id', 'mocked_prover_key', '000000000000000000000000Prover01', pool_handle)
    verifier = await setup_actor('Verifier', 'mocked_verifier_id', 'mocked_verifier_key', '00000000000000000000000Verifier1', pool_handle)


    # Create schema and corresponding definition
    unique_schema_name, schema_id, issuer = await create_schema(schema, issuer)
    issuer = await create_credential_definition(issuer, schema_id, unique_schema_name, revocable = False)

    # Issue credential
    issuer = await offer_credential(issuer, unique_schema_name)
    send_data(issuer['authcrypted_certificate_cred_offer'])
    prover['authcrypted_certificate_cred_offer'] = receive_data()

    prover = await receive_credential_offer(prover, unique_schema_name)
    prover = await request_credential(prover, cred_request, unique_schema_name)
    send_data(prover['authcrypted_certificate_cred_request'])
    issuer['authcrypted_certificate_cred_request'] = receive_data()


    issuer['prover_certificate_cred_values'] = prover[unique_schema_name + '_cred_values']
    issuer = await create_and_send_credential(issuer, unique_schema_name)
    send_data(issuer['authcrypted_certificate_cred'])
    prover['authcrypted_certificate_cred'] = receive_data()

    prover = await store_credential(prover, unique_schema_name)
    

    # Prover onboarded with verifier
    verifier['did_for_prover'], verifier['key_for_prover'], prover['did_for_verifier'], prover['key_for_verifier'], \
    verifier['prover_connection_response'] = await onboarding(verifier, prover)
    verifier = await request_proof_of_credential(verifier, proof_request)
    send_data(verifier['authcrypted_proof_request'])
    prover['authcrypted_proof_request'] = receive_data()

    prover = await create_proof_of_credential(prover, self_attested_attributes, requested_attributes,
                                              requested_predicates, non_issuer_attributes)
    
    send_data(prover['authcrypted_proof'])
    verifier['authcrypted_proof'] = receive_data()

    verifier = await verify_proof(verifier, assertions_to_make)

    await teardown(pool_name, pool_handle, [steward, issuer, prover, verifier])

    print('Credential verified.')


# Loads examples in the example_data folder
def load_example_data(path):
    example_data = {}
    for filename in os.listdir(path):
        with open(path + filename) as file_:
            example_data[filename.replace('.json', '')] = json.load(file_)
    cred_request = example_data['credential_request']
    # Specify schema version
    schema = example_data['credential_schema']['restricted']
    proof_request = example_data['proof_request']['request']
    assertions_to_make = example_data['proof_request']['assertions_to_make']
    # Don't json.dump this
    self_attested_attributes = example_data['proof_creation']['self_attested_attributes']
    requested_attributes = example_data['proof_creation']['requested_attributes']
    requested_predicates = example_data['proof_creation']['requested_predicates']
    non_issuer_attributes = example_data['proof_creation']['non_issuer_attributes']
    return cred_request, schema, proof_request, assertions_to_make, self_attested_attributes, \
           requested_attributes, requested_predicates, non_issuer_attributes


async def setup_actor(name, id_, key, seed, pool_handle = 1):
    actor = {
        'name': name,
        'wallet_config': json.dumps({'id': id_}),
        'wallet_credentials': json.dumps({'key': key}),
        'pool': pool_handle,
        'seed': seed,
        'role': 'TRUST_ANCHOR'
    }
    try:
        await wallet.create_wallet(actor['wallet_config'], actor['wallet_credentials'])
    except IndyError as ex:
        if ex.error_code == ErrorCode.WalletAlreadyExistsError:
            pass
    actor['wallet'] = await wallet.open_wallet(actor['wallet_config'], actor['wallet_credentials'])
    # Generate DID from seed
    actor['did_info'] = json.dumps({'seed': actor['seed']})
    actor['did'], actor['key'] = await did.create_and_store_my_did(actor['wallet'], actor['did_info'])
    return actor


if __name__ == '__main__':
    run_coroutine(run)
    time.sleep(1)  # FIXME waiting for libindy thread complete
