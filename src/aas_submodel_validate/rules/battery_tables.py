"""Generated from the battery-passport requirements indexes. Do not edit.

Written by `tools/extract_battery_rules.py`; run it after the indexes
move. The source edition and the hashes it was built from are below, so
a finding can name the template it read: IDTA 02035-5 published 1.0.2 in
August 2026, and a table that does not say which edition it is stops
being true without saying so.
"""


#: The edition of every template a row below was read from.
SOURCE_EDITION = 'IDTA 02035-1 V1.0, IDTA 02035-4 V1.0.1, IDTA 02035-5 V1.0.2'

#: Submodel identifiers more than one published template claims.
SHARED_SUBMODEL_IDS = {
    '0173-1#01-AHF578#003':
        ('IDTA 02004', 'IDTA 02035-2'),
    'https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0':
        ('IDTA 02023', 'IDTA 02035-3'),
}

#: Elements the template allows to be absent that a legal reading
#: requires **of every battery category the source names**. Every
#: field here is one a finding has to say.
LAW_REQUIRES_TEMPLATE_OPTIONAL = (
    {
        'element': 'idta-smt:idta-02035-4:TechnicalData/TechnicalPropertyAreas/RoundTripEnergyEfficiency/EnergyRoundTripEfficiencyFade',
        'template': 'IDTA 02035-4',
        'template_version': 'V1.0.1',
        'submodel_semantic_id': 'https://admin-shell.io/idta/digitalbatterypassport/TechnicalData/1/0',
        'submodel_sha256': 'a90774b959c766efe596243c39934df266ee34ce1132ba85f4b382efff842cb0',
        'element_id_short': 'EnergyRoundTripEfficiencyFade',
        'element_semantic_id': '0173-1#02-ABL827#002',
        'cardinality': 'ZeroToOne',
        'text': 'round trip energy efficiency fade DIN DKE Spec 99100 chapter reference: 6.7.4.5',
        'says_mandatory': ('longlist:77',),
        'citations': ('Annex IV Part A (4)',),
        'categories': (('EV', 'required-by-batteries-regulation'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'required-by-batteries-regulation'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
)

#: The same disagreement where it depends on the battery's
#: category, which no rule here can read yet. Reported by
#: nothing: the capacity threshold for exhaustion is required
#: for electric vehicles and marked *not to be filled* for
#: everything else, so a finding that ignored the category
#: would tell one manufacturer to add what another's guidance
#: forbids. Carried so the coverage note can count what it is
#: not saying.
CONDITIONAL_ON_CATEGORY = (
    {
        'element': 'idta-smt:idta-02035-1:BatteryNameplate/DateOfPuttingIntoService',
        'template': 'IDTA 02035-1',
        'template_version': 'V1.0',
        'submodel_semantic_id': 'https://admin-shell.io/idta/digitalbatterypassport/nameplate/1/0/Nameplate',
        'submodel_sha256': '0eec79b05fde3d62a287248d6dd8d17643bfa2b0bb8e2e4cecad04a28b90ccfe',
        'element_id_short': 'DateOfPuttingIntoService',
        'element_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.digital_nameplate:1.0.0#dateOfPuttingIntoService',
        'cardinality': 'ZeroToOne',
        'text': 'date of putting into service',
        'says_mandatory': ('longlist:16',),
        'citations': ('Annex VII Part B (1)',),
        'categories': (('EV', 'voluntary'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'voluntary'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
    {
        'element': 'idta-smt:idta-02035-4:TechnicalData/TechnicalPropertyAreas/CapacityEnergyVoltage/CapacityFade',
        'template': 'IDTA 02035-4',
        'template_version': 'V1.0.1',
        'submodel_semantic_id': 'https://admin-shell.io/idta/digitalbatterypassport/TechnicalData/1/0',
        'submodel_sha256': 'a90774b959c766efe596243c39934df266ee34ce1132ba85f4b382efff842cb0',
        'element_id_short': 'CapacityFade',
        'element_semantic_id': '0173-1#02-ABL828#002',
        'cardinality': 'ZeroToOne',
        'text': 'capacity fade DIN DKE Spec 99100 chapter reference: 6.7.2.4',
        'says_mandatory': ('ec-datapoints:52', 'longlist:61'),
        'citations': ('Annex IV Part A (1)', 'Annex IV (2)'),
        'categories': (('EV', 'required'), ('LMT', 'required'), ('industrial-above-2kWh', 'certain-cases'), ('industrial-other-above-2kWh', 'required-by-batteries-regulation'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
    {
        'element': 'idta-smt:idta-02035-4:TechnicalData/TechnicalPropertyAreas/Lifetime/CapacityThresholdExhaustion',
        'template': 'IDTA 02035-4',
        'template_version': 'V1.0.1',
        'submodel_semantic_id': 'https://admin-shell.io/idta/digitalbatterypassport/TechnicalData/1/0',
        'submodel_sha256': 'a90774b959c766efe596243c39934df266ee34ce1132ba85f4b382efff842cb0',
        'element_id_short': 'CapacityThresholdExhaustion',
        'element_semantic_id': '0173-1#02-ABL838#002',
        'cardinality': 'ZeroToOne',
        'text': 'capacity threshold for exhaustion',
        'says_mandatory': ('ec-datapoints:33', 'longlist:90'),
        'citations': ('Annex XIII (1k)',),
        'categories': (('EV', 'required'), ('LMT', 'not-to-be-filled'), ('industrial-above-2kWh', 'not-to-be-filled'), ('industrial-other-above-2kWh', 'not-stated'), ('industrial-stationary-above-2kWh', 'not-stated')),
    },
    {
        'element': 'idta-smt:idta-02035-5:ProductCondition/EnergyThroughput',
        'template': 'IDTA 02035-5',
        'template_version': 'V1.0.2',
        'submodel_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#ProductCondition',
        'submodel_sha256': 'fc3c81609ca4f923b77ca14d21c8dcf5202e385c94b5090b65148fcec870ab75',
        'element_id_short': 'EnergyThroughput',
        'element_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#energyThroughput',
        'cardinality': 'ZeroToOne',
        'text': 'energy throughput',
        'says_mandatory': ('longlist:88',),
        'citations': ('Annex VII Part B (2)',),
        'categories': (('EV', 'not-stated'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'not-stated'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
    {
        'element': 'idta-smt:idta-02035-5:ProductCondition/CapacityThroughput',
        'template': 'IDTA 02035-5',
        'template_version': 'V1.0.2',
        'submodel_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#ProductCondition',
        'submodel_sha256': 'fc3c81609ca4f923b77ca14d21c8dcf5202e385c94b5090b65148fcec870ab75',
        'element_id_short': 'CapacityThroughput',
        'element_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#capacityThroughput',
        'cardinality': 'ZeroToOne',
        'text': 'capacity throughput',
        'says_mandatory': ('longlist:89',),
        'citations': ('Annex VII Part B (3)',),
        'categories': (('EV', 'not-stated'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'not-stated'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
    {
        'element': 'idta-smt:idta-02035-5:ProductCondition/RemainingCapacity',
        'template': 'IDTA 02035-5',
        'template_version': 'V1.0.2',
        'submodel_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#ProductCondition',
        'submodel_sha256': 'fc3c81609ca4f923b77ca14d21c8dcf5202e385c94b5090b65148fcec870ab75',
        'element_id_short': 'RemainingCapacity',
        'element_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#remainingCapacity',
        'cardinality': 'ZeroToOne',
        'text': 'remaining capacity',
        'says_mandatory': ('longlist:60',),
        'citations': ('Annex VII Part A (1)',),
        'categories': (('EV', 'voluntary'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'voluntary'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
    {
        'element': 'idta-smt:idta-02035-5:ProductCondition/RemainingPowerCapability',
        'template': 'IDTA 02035-5',
        'template_version': 'V1.0.2',
        'submodel_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#ProductCondition',
        'submodel_sha256': 'fc3c81609ca4f923b77ca14d21c8dcf5202e385c94b5090b65148fcec870ab75',
        'element_id_short': 'RemainingPowerCapability',
        'element_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#remainingPowerCapability',
        'cardinality': 'ZeroToOne',
        'text': 'remaining power capability',
        'says_mandatory': ('longlist:70',),
        'citations': ('Art. 10: Annex IV (3) (only definition of power)', 'Annex VII Part A (2) "where possible, remaining power capability"', 'Annex IV Part B (4) --> measurement at 80 % SoC and 20% SoC required'),
        'categories': (('EV', 'voluntary'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'voluntary'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
    {
        'element': 'idta-smt:idta-02035-5:ProductCondition/RemainingRoundTripEnergyEfficiency',
        'template': 'IDTA 02035-5',
        'template_version': 'V1.0.2',
        'submodel_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#ProductCondition',
        'submodel_sha256': 'fc3c81609ca4f923b77ca14d21c8dcf5202e385c94b5090b65148fcec870ab75',
        'element_id_short': 'RemainingRoundTripEnergyEfficiency',
        'element_semantic_id': 'urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#remainingRoundTripEnergyEfficiency',
        'cardinality': 'ZeroToOne',
        'text': 'remaining round trip energy efficiency',
        'says_mandatory': ('longlist:76',),
        'citations': ('Art. 10: Annex IV Part A (4)', 'Article 14: Annex VII Part A (3)', 'Annex IV (6)'),
        'categories': (('EV', 'not-stated'), ('LMT', 'required-by-batteries-regulation'), ('industrial-other-above-2kWh', 'not-stated'), ('industrial-stationary-above-2kWh', 'required-by-batteries-regulation')),
    },
)
