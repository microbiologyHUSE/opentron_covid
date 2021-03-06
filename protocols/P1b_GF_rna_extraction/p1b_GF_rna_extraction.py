import math
from opentrons.types import Point
from opentrons import robot
from opentrons import protocol_api
from opentrons import labware
import time
import os
import numpy as np
from timeit import default_timer as timer
import json
from datetime import datetime
import csv
import subprocess

# metadata
metadata = {
    'protocolName': 'RNA Extraction Version 2',
    'author': 'Matias Bonet & Antoni Morla. based on: Malen Aguirregabiria,Aitor Gastaminza & José Luis Villanueva (jlvillanueva@clinic.cat)',
    'source': 'Hospital Son Espases Palma',
    'apiLevel': '2.3',
    'description': 'Protocol for rna extraction'
}

'''
'technician': 'Toni',
'date': '$date'
'''
# Defined variables
##################
NUM_SAMPLES = 24
steps = []  # Steps you want to execut
set_temp_on = False  # Do you want to start temperature module?
temperature = 65  # Set temperature. It will be uesed if set_temp_on is set to True
set_mag_on = True  # Do you want to start magnetic module?
mag_height = 7  # Height needed for NEST deepwell in magnetic deck

robot = None
use_waits = True

num_cols = math.ceil(NUM_SAMPLES/8)

diameter_screwcap = 8.1  # Diameter of the screwcap
volume_cone = 57  # Volume in ul that fit in the screwcap cone
area_section_screwcap = (np.pi * diameter_screwcap**2) / 4
h_cone = (volume_cone * 3 / area_section_screwcap)


air_gap_vol = 10
air_gap_r1 = 0
air_gap_sample = 0
log_folder = 'rna_extraction_logs'


def run(ctx: protocol_api.ProtocolContext):

    # Init protocol run
    run = ProtocolRun(ctx)

    minutos = 1 # Tendria que ser 60 pero para testeo lo pongo a 10
    run.add_step(description="65C Incubation", wait_time=5*minutos)  # 5* 60 minutos 1
    run.add_step(description="Transfer From temperature to magnet 485ul")  # 2
    run.add_step(description="Magnetic on: 10 minutes",
                 wait_time=10*minutos)  # 10*60 3
    run.add_step(
        description="Extraer liquido no beads. Slot 7 - Piscina Slot 3")  # 4
    run.add_step(description="Magnetic off")  # 5
    run.add_step(
        description="Replace tips, add WB, add ETOH, vaciar piscina y trash. Cambiar nuevo DW SLOT 10")  # INTERACTION 6

    # Add WB
    run.add_step(description="Add 500ul de WB  a los beats Slot 4 - 7 ")  # 7
    run.add_step(description="Magnetic on: 2 minutes", wait_time=2*minutos)  # 2*60 8
    run.add_step(description="Extraer liquido no beats. Slot 7 - Slot 3")  # 9
    run.add_step(description="Magnetic off")  # 10

    # Add ETOH First step
    run.add_step(description="Add 500ul de etoh a los beats Slot 8 - 7 ")  # 11
    run.add_step(description="Magnetic on: 2 minutes", wait_time=2*minutos)  # 2*60 12
    run.add_step(description="Extraer liquido no beats. Slot 7 - Slot 3")  # 13
    run.add_step(description="Magnetic off")  # 14

    run.add_step(description="Replace tips etc. add elution")
    # Add ETOH Second step
    run.add_step(description="Add 250ul de etoh a los beats Slot 8 - 7 ")  # 15
    run.add_step(description="Magnetic on: 2 minutes", wait_time=2*minutos)  # 2*60 16
    run.add_step(description="Extraer liquido no beats. Slot 7 - Slot 3")  # 17
    run.add_step(description="Secar durante 10 minutos",
                 wait_time=10)  # 10 * 60 18
    run.add_step(description="Magnetic off")  # 19
    run.add_step(
        description="Add elution move to temperature same tip 4 -> 7 -> 10")  # 20
    run.add_step(description="65C Incubation 10'",
                 wait_time=10)  # 10 * 60 # 21
    
    run.add_step(description="Replace tips, change deepwell slot 7 magnet")
    run.add_step(description="Move 50ul from temp to magnet 10-7")  # 22
    run.add_step(description="Magnetic on: 3 minutes",wait_time=3*minutos)  #23 3 * 60 27
    run.add_step(description="Move 50ul Magnet Final destination 7-> 2")  # 24
    run.add_step(description="Magnetic off")  # 25


    # execute avaliaible steps
    run.init_steps(steps)

    ##################################
    # Define desk
    moving_type = "axygen_96_wellplate_2000ul"
    moving_type_sim = "biorad_96_wellplate_200ul_pcr"

    # Destination plate SLOT 2
    try:
        aw_slot = ctx.load_labware(moving_type, 2)
    except:
        moving_type = moving_type_sim
        aw_slot = ctx.load_labware(moving_type, 2)

    aw_wells = aw_slot.wells()[:NUM_SAMPLES]
    aw_wells_multi = aw_slot.rows()[0][:num_cols]

    wbeb_slot = ctx.load_labware(
        'nest_12_reservoir_15mL', 4)
    wbeb_wells_multi = wbeb_slot.rows()[0][:num_cols]

    #Set up trash1
    trash_pool_slot = ctx.load_labware(
        'nest_1_reservoir_195ml', 3)
    trash_pool_wells_multi = trash_pool_slot.rows()[0][:num_cols]


    # # Magnetic module plus NEST_Deep_well_reservoire
    magdeck = ctx.load_module('magnetic module gen2', 7)
    magdeck.disengage()
    mag_slot = magdeck.load_labware(moving_type)
    mag_wells_multi = mag_slot.rows()[0][:num_cols]

    # Ethanol Pool
    etoh_slot = ctx.load_labware(
        'nest_1_reservoir_195ml', 1)
    etoh_wells_multi = etoh_slot.rows()[0][:num_cols]

    # Temperature module plus NEST_Deep_well_reservoire
    tempdeck = ctx.load_module('tempdeck', 10)
    temp_slot = tempdeck.load_labware(moving_type)
    temp_wells_multi = temp_slot.rows()[0][:num_cols]

    # Mount pippets and set racks
    tips300_8 = ctx.load_labware('opentrons_96_filtertiprack_200ul', "8")
    tips300_9 = ctx.load_labware('opentrons_96_filtertiprack_200ul', "9")
    tips300_6 = ctx.load_labware('opentrons_96_filtertiprack_200ul', "6")
    tips300_5 = ctx.load_labware('opentrons_96_filtertiprack_200ul', "5")

    #run.mount_right_pip('p20_single_gen2', tip_racks=[tips20], capacity=20)
    run.mount_left_pip('p300_multi_gen2', tip_racks=[
                       tips300_8,tips300_9, tips300_6, tips300_5], capacity=200, multi=True)

    run.set_pip("left")
    ############################################################################
    # STEP 1: Incubation at 65ºC
    ############################################################################
    if (run.next_step()):
        if (set_temp_on):
            tempdeck.set_temperature(temperature)
        run.finish_step()
        tempdeck.deactivate()

    ############################################################################
    # STEP 2: Transfer From temperature to magnet 485ul
    ############################################################################
    if (run.next_step()):

        run.set_pip("left")  # p300 multi
        liquid = Reagent(name='MIX_HOT',
                         num_wells=1,  # change with num samples
                         delay=0,
                         flow_rate_aspirate=3,  # Original 0.5
                         flow_rate_dispense=3,  # Original 1
                         flow_rate_aspirate_mix=15,
                         flow_rate_dispense_mix=25,
                         reagent_reservoir_volume=485,
                         h_cono=4,
                         v_fondo=4 * math.pi * 4 ** 3 / 3)

        air_gap_vol = 3
        disposal_height = -5
        pickup_height = 1

        for source, destination in zip(temp_wells_multi, mag_wells_multi):
            run.pick_up()
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height,
                            rinse=True,touch_tip=True)
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height,
                            rinse=True,touch_tip=True)
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=135, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height, rinse=True,touch_tip=True)
            run.drop_tip()

        run.finish_step()

    ############################################################################
    # STEP 3: Magnet on 10 minutos
    ############################################################################
    if (run.next_step()):
        if (set_mag_on):
            magdeck.engage(height=mag_height)
        run.finish_step()
    
    # Extraer liquido sin tocar los beats. Slot 7 - Piscina Slot 3
    def move_magnet_to_trash(move_vol_steps=3):
        run.set_pip("left")  # p300 multi
        # Sobre nadante primer paso
        liquid = Reagent(name='Sobrenadante',
                         num_wells=1,  # change with num samples
                         delay=0,
                         flow_rate_aspirate=0.2,  # Original 0.5
                         flow_rate_dispense=3,  # Original 1
                         reagent_reservoir_volume=528,
                         h_cono=4,
                         v_fondo=4 * math.pi * 4 ** 3 / 3)

        air_gap_vol = 3
        pickup_height = 1
        disposal_height = 0
        # Hay que revisar los offsets para el movimiento este
        for source in mag_wells_multi:
            destination=trash_pool_wells_multi[0]
            # Replace this
            run.pick_up()
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height)

            # Patch for last step of etho 250ul instead of 500
            if(move_vol_steps == 3):
                run.move_volume(reagent=liquid, source=source,
                                dest=destination, vol=175, air_gap_vol=air_gap_vol,
                                pickup_height=pickup_height, disp_height=disposal_height)

            # We want to empty does not matter if we aspirate more
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height)
            run.drop_tip()


    ############################################################################
    # STEP 4: Extract liquid from magnet to liquid trash
    ############################################################################
    if (run.next_step()):
        move_magnet_to_trash()
        run.finish_step()

    ############################################################################
    # STEP 5: Magnet off
    ############################################################################
    if (run.next_step()):
        magdeck.disengage()
        run.finish_step()

    ############################################################################
    # STEP 6: Pause to replace
    ############################################################################
    if (run.next_step()):
        run.blink()
        ctx.pause(
            'Replace tips, add WB, add ETOH, vaciar piscina y trash. Cambiar nuevo DW SLOT 10')
        run.reset_pip_count(run.get_current_pip())
        run.finish_step()

    ############################################################################
    # STEP 7: Add 500ul de WB a los bits 4 - 7
    ############################################################################
    if (run.next_step()):
        run.set_pip("left")  # p300 multi
        vol_wb = 485
        wb = Reagent(name='WB Wash buffer',
                        flow_rate_aspirate=0.25,
                        flow_rate_dispense=0.25,
                        flow_rate_dispense_mix=0.25,
                        flow_rate_aspirate_mix=0.25,
                        delay=1,
                        reagent_reservoir_volume=vol_wb*(NUM_SAMPLES+1)*1.1,
                        h_cono=1.95,
                        v_fondo=695,
                        )

        run.comment(wb.get_volumes_fill_print(),add_hash=True)
        wb.set_positions(wbeb_slot.rows()[0][0:wb.num_wells])

        air_gap_vol = 3
        disposal_height = -1  # Arriba y el último paso lo hacemos dentro
        pool_area = 8.3*71.1
        
        for destination in mag_wells_multi:
            run.pick_up()
            
            pickup_height= wb.calc_height(
                    pool_area, 175*8)

            run.move_volume(reagent=liquid, source=wb.get_current_position(),
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height
                            )
            pickup_height= wb.calc_height(
                    pool_area, 175*8)

            run.move_volume(reagent=liquid, source=wb.get_current_position(),
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height)

            # This will be drop inside
            pickup_height= wb.calc_height(
                    pool_area, 175*8)

            disposal_height=2
            run.move_volume(reagent=liquid, source=wb.get_current_position(),
                            dest=destination, vol=135, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height-3)

            run.custom_mix(liquid, location=destination, vol=50,
                           rounds=10, blow_out=True, mix_height=0)
            run.drop_tip()

        run.finish_step()

    ############################################################################
    # STEP 8: Magnet on 2 minutos
    ############################################################################
    if (run.next_step()):
        if (set_mag_on):
            magdeck.engage(height=mag_height)
        run.finish_step()
    ############################################################################
    # STEP 9: Extract liquid from magnet to liquid trash
    ############################################################################
    if (run.next_step()):
        move_magnet_to_trash()
        run.finish_step()

    ############################################################################
    # STEP 10: Magnet off
    ############################################################################
    if (run.next_step()):
        magdeck.disengage()
        run.finish_step()

    # Used twice in the next steps

    vol_etoh=500+250
    etoh = Reagent(name='ETOH',
                        flow_rate_aspirate=1,
                        flow_rate_dispense=1,
                        flow_rate_dispense_mix=4,
                        flow_rate_aspirate_mix=4,
                        delay=1,
                        reagent_reservoir_volume=vol_etoh*(NUM_SAMPLES+1),
                        vol_well_max=195000,
                        rinse=True,
                        num_wells=1,
                        h_cono=1.95,
                        v_fondo=695)

    run.comment(etoh.get_volumes_fill_print(),add_hash=True)

    ############################################################################
    # STEP 11: Add 500ul de etoh a los beats Slot 8 - 7
    ############################################################################
    if (run.next_step()):

        run.set_pip("left")  # p300 multi
        liquid = etoh
        air_gap_vol = 3
        disposal_height = -1  # Arriba y el último paso lo hacemos dentro
        pickup_height = 1

        for source, destination in zip(etoh_wells_multi, mag_wells_multi):
            run.pick_up()
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height
                            )
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height)

            # This will be drop inside
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=135, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height-3)

            run.custom_mix(liquid, location=destination, vol=50,
                           rounds=5, blow_out=True, mix_height=0)

            run.drop_tip()
        run.finish_step()

    ############################################################################
    # STEP 12: Magnet on 10 minutos
    ############################################################################
    if (run.next_step()):
        if (set_mag_on):
            magdeck.engage(height=mag_height)
        run.finish_step()
    ############################################################################
    # STEP 13: Extract liquid from magnet to liquid trash
    ############################################################################
    if (run.next_step()):
        move_magnet_to_trash()
        run.finish_step()

    ############################################################################
    # STEP 14   : Magnet off
    ############################################################################
    if (run.next_step()):
        magdeck.disengage()
        run.finish_step()

    ############################################################################
    # STEP 15: Run pause
    ############################################################################
    if (run.next_step()):
        run.blink()
        ctx.pause(
            'Replace tips,add elution')
        run.reset_pip_count(run.get_current_pip())
        run.finish_step()

    
    ############################################################################
    # STEP 16: Add 250 de etoh a los beats Slot 8 - 7
    ############################################################################
    if (run.next_step()):

        run.set_pip("left")  # p300 multi
        liquid = etoh
        air_gap_vol = 3
        disposal_height = -1  # Arriba y el último paso lo hacemos dentro
        pickup_height = 1

        for source, destination in zip(etoh_wells_multi, mag_wells_multi):
            run.pick_up()
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=175, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height
                            )
            # This will be drop inside
            run.move_volume(reagent=liquid, source=source,
                            dest=destination, vol=125, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height-3)
            
            run.custom_mix(liquid, location=destination, vol=50,
                           rounds=5, blow_out=True, mix_height=0)


            run.drop_tip()

    ############################################################################
    # STEP 17: Magnet on 2 minutos
    ############################################################################
    if (run.next_step()):
        if (set_mag_on):
            magdeck.engage(height=mag_height)
        run.finish_step()

    ############################################################################
    # STEP 18: Extract liquid from magnet to liquid trash
    ############################################################################
    if (run.next_step()):
        move_magnet_to_trash(move_vol_steps=2)
        run.finish_step()

    ############################################################################
    # STEP 19: Secar durante 10 minutos
    ############################################################################
    if (run.next_step()):
        run.finish_step()
        run.blink()
        ctx.pause(
            'Revisa que esté seco')

    ############################################################################
    # STEP 20: Magnet off
    ############################################################################
    if (run.next_step()):
        magdeck.disengage()
        run.finish_step()

    ############################################################################
    # STEP 21: Add elution move to temperature same tip 4 -> 7 -> 10
    ############################################################################
    # Used to move from temp to magnet and from magnet to destionation
    elu_beads = Reagent(name='BeatsToHot',
                        num_wells=1,  # change with num samples
                        delay=0,
                        flow_rate_aspirate=3,  # Original 0.5
                        flow_rate_dispense=3,  # Original 1
                        flow_rate_aspirate_mix=15,
                        flow_rate_dispense_mix=25,
                        reagent_reservoir_volume=528,
                        h_cono=4,
                        v_fondo=4 * math.pi * 4 ** 3 / 3)

    if (run.next_step()):
        # to liquid types
        vol_eb = 50
        elution = Reagent(name='Elution Buffer',
                        flow_rate_aspirate=2,
                        flow_rate_dispense=2,
                        flow_rate_dispense_mix=4,
                        flow_rate_aspirate_mix=4,
                        reagent_reservoir_volume=vol_eb*(NUM_SAMPLES+1),
                        delay=1, 
                        num_wells=1,
                        h_cono=1.95,
                        v_fondo=695,
                        rinse_loops=3)
        
        run.comment(elution.get_volumes_fill_print(),add_hash=True)
        elution.set_positions(wbeb_slot.rows()[0][11:12])

        air_gap_vol = 3
        disposal_height = -5
        pickup_height = 1
        for dest_source, destination in zip(mag_wells_multi, temp_wells_multi):
            run.pick_up()
            run.move_volume(reagent=elution, source=elution.get_current_position(),
                            dest=dest_source, vol=vol_eb, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height
                            )

            run.custom_mix(elu_beads, location=dest_source, vol=100,
                           rounds=10, blow_out=True, mix_height=0)

            # This will be drop inside
            run.move_volume(reagent=elu_beads, source=dest_source,
                            dest=destination, vol=50, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height-3)

            run.drop_tip()

        run.finish_step()

    ############################################################################
    # STEP 22: Incubation at 65ºC
    ############################################################################
    if (run.next_step()):
        if (set_temp_on):
            tempdeck.set_temperature(temperature)
        run.finish_step()
    
    ############################################################################
    # STEP 23: Pause to reset tips, replace deep well SLOT 7 and add DeepWell on SLOT2
    ############################################################################
    if (run.next_step()):
        run.blink()
        ctx.pause(
            'Replace tips, change DeepWell on Magnet SLOT 7, and add final Deepwell on SLOT 2')
        run.reset_pip_count(run.get_current_pip())
        run.finish_step()

    ############################################################################
    # STEP 24: Move from temp to magnet
    ############################################################################
    if (run.next_step()):
        result = Reagent(name='Elution+magnets',
                         num_wells=1,  # change with num samples
                         delay=0,
                         flow_rate_aspirate=3,  # Original 0.5
                         flow_rate_dispense=3,  # Original 1
                         flow_rate_aspirate_mix=15,
                         flow_rate_dispense_mix=25,
                         reagent_reservoir_volume=528,
                         h_cono=4,
                         v_fondo=4 * math.pi * 4 ** 3 / 3)

        for source, destination in zip(temp_wells_multi, mag_wells_multi):
            run.pick_up()
            run.move_volume(reagent=result, source=source,
                            dest=destination, vol=1, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height
                            )
            run.drop_tip()

        run.finish_step()

    ############################################################################
    # STEP 25: Magnet on 3 minutos
    ############################################################################
    if (run.next_step()):
        if (set_mag_on):
            magdeck.engage(height=mag_height)
        run.finish_step()

    ############################################################################
    # STEP 26: Move from magnet to final output slot 2
    ############################################################################
    if (run.next_step()):
        result = Reagent(name='Elution-magnets',
                         num_wells=1,  # change with num samples
                         delay=0,
                         flow_rate_aspirate=3,  # Original 0.5
                         flow_rate_dispense=3,  # Original 1
                         flow_rate_aspirate_mix=15,
                         flow_rate_dispense_mix=25,
                         reagent_reservoir_volume=528,
                         h_cono=4,
                         v_fondo=4 * math.pi * 4 ** 3 / 3)
        for source, destination in zip(mag_wells_multi,aw_wells_multi):
            run.pick_up()
            run.move_volume(reagent=result, source=source,
                            dest=destination, vol=50, air_gap_vol=air_gap_vol,
                            pickup_height=pickup_height, disp_height=disposal_height
                            )
            run.drop_tip()

        run.finish_step()

    ############################################################################
    # STEP 27: Magnet off
    ############################################################################
    if (run.next_step()):
        magdeck.disengage()
        run.finish_step()

    run.log_steps_time()
    run.blink()
    ctx.comment('Finished! \nMove plate to PCR')

##################
# Custom function
##################
class Reagent:
    def __init__(self, name, flow_rate_aspirate, flow_rate_dispense,
                 reagent_reservoir_volume,  h_cono, v_fondo, vol_well_max=12000, num_wells=-1,rinse=False, delay=0,
                 tip_recycling='none', rinse_loops=3, flow_rate_dispense_mix=2, flow_rate_aspirate_mix=2):

        self.name = name
        self.flow_rate_aspirate = flow_rate_aspirate
        self.flow_rate_dispense = flow_rate_dispense
        self.flow_rate_aspirate_mix = flow_rate_aspirate_mix
        self.flow_rate_dispense_mix = flow_rate_dispense_mix
        self.rinse = bool(rinse)
        self.reagent_reservoir_volume = reagent_reservoir_volume
        self.delay = delay  # Delay of reagent in dispense
            
        self.col = 0
        self.h_cono = h_cono
        self.v_cono = v_fondo
        self.tip_recycling = tip_recycling
        self.rinse_loops = rinse_loops

        
        if(num_wells!=-1):
            if(num_wells==1):
                self.num_wells = num_wells
                self.vol_well = self.reagent_reservoir_volume
                self.vol_last_well = self.vol_well
                self.vol_well_max = vol_well_max

            else:   
                self.num_wells = num_wells
                #IF manually made we set up all to have the same
                self.vol_well_max = self.reagent_reservoir_volume/self.num_wells
                self.vol_last_well = self.vol_well_max
                self.vol_well = self.vol_last_well
        else:
            self.vol_well_max = vol_well_max-self.v_cono
            num_wells = math.floor(self.reagent_reservoir_volume/self.vol_well_max)
            self.vol_last_well = math.ceil(self.reagent_reservoir_volume-num_wells*self.vol_well_max)
            if(self.vol_last_well>0):
                self.num_wells = num_wells+1
            else:
                self.num_wells = num_wells
            
            if(self.num_wells==1):
                self.vol_well = self.vol_last_well
                self.vol_well_max = self.vol_last_well
            else:
                self.vol_well = math.ceil(self.vol_well_max)
    
    def get_current_position(self):
        
        return self.reagent_reservoir[self.col]
    
    def set_positions(self,labware_address):
        self.reagent_reservoir = labware_address

    def get_volumes_fill_print(self):
        if(self.num_wells==1):
            return "===> '%s' has %s wells with %s Volume"%(
                                            self.name,
                                            self.num_wells,
                                            self.vol_last_well+self.v_cono
                                            )

        else:
            return "===> '%s' has %s wells with %s Volume. Volumen_last_well: %s"%(self.name,
                                            self.num_wells-1,
                                            self.vol_well_max+self.v_cono,
                                            self.vol_last_well+self.v_cono)

    def next_column(self):
        # Move to next position inside reagent
        self.col =self.col+1
        if(self.col<self.num_wells):
            self.vol_well = self.vol_well_max
        else:
            self.vol_well = self.vol_last_well


    def calc_height(self, cross_section_area, aspirate_volume,
                    min_height=0.3):

        if self.vol_well < aspirate_volume:
            # column selector position; intialize to required number
            self.next_column() 
        
        height = (self.vol_well - aspirate_volume) / cross_section_area - 5
        self.vol_well = self.vol_well - aspirate_volume

        if height < min_height:
            height = min_height

        return height

    def divide_volume(self, volume, max_vol):

        num_transfers = math.ceil(volume/max_vol)
        vol_roundup = math.ceil(volume/num_transfers)
        last_vol = volume - vol_roundup*(num_transfers-1)
        vol_list = [vol_roundup for v in range(1, num_transfers)]
        vol_list.append(last_vol)
        return vol_list

class ProtocolRun:
    def __init__(self, ctx):
        self.ctx = ctx
        self.step_list = []
        self.step = 0

        # Folder and file_path for log time
        folder_path = '/var/lib/jupyter/notebooks/'+log_folder
        if not self.ctx.is_simulating():
            if not os.path.isdir(folder_path):
                os.mkdir(folder_path)
            self.file_path = folder_path + \
                '/rna_extraction_%s.tsv' % datetime.now().strftime("%d_%m_%Y_%H_%M_%S")

        self.selected_pip = "right"
        self.pips = {"right": {}, "left": {}}

    def add_step(self, description, execute=False, wait_time=0):
        self.step_list.append(
            {'execute': execute, 'description': description, 'wait_time': wait_time, 'execution_time': 0})

    def init_steps(self, steps):
        if(len(steps) > 0):
            for index in steps:
                if(index <= len(self.step_list)):
                    self.set_execution_step(index-1, True)
                else:
                    print("Step index out of range")
        else:
            for index, step in enumerate(self.step_list):
                self.set_execution_step(index, True)


        self.comment("###############################################")
        self.comment("You are about to run %s samples" % (NUM_SAMPLES))
        for step in self.step_list:
            if(step['execute']):
                self.comment(step["description"])
        self.blink(5)
        self.pause("Are you sure the set up is correct? \n Check the desk before continue\n press resume")
        self.comment("###############################################")

    def set_execution_step(self, index, value):
        self.step_list[index]["execute"] = value

    def get_current_step(self):
        return self.step_list[self.step]

    def next_step(self):
        if self.step_list[self.step]['execute'] == False:
            self.step += 1
            return False

        #self.comment(self.step_list[self.step]['description'], add_hash=True)
        self.start = datetime.now()
        return True

    def finish_step(self):
        if (self.get_current_step()["wait_time"] > 0 and use_waits):
            self.ctx.delay(seconds=int(self.get_current_step()[
                "wait_time"]), msg=self.get_current_step()["description"])
        if (self.get_current_step()["wait_time"] > 0 and not use_waits):
            self.comment("We simulate a wait of:%s seconds" %
                          self.get_current_step()["wait_time"])
        end = datetime.now()
        time_taken = (end - self.start)
        self.comment('Step ' + str(self.step + 1) + ': ' +
                     self.step_list[self.step]['description'] + ' took ' + str(time_taken), add_hash=True)

        self.step_list[self.step]['execution_time'] = str(time_taken)
        self.step += 1
        self.log_steps_time()

    def log_steps_time(self):
        # Export the time log to a tsv file
        if not self.ctx.is_simulating():
            with open(self.file_path, 'w') as f:
                f.write('STEP\texecution\tdescription\twait_time\texecution_time\n')
                row = ""
                for step in self.step_list:
                    row = ('{}\t{}\t{}\t{}').format(
                        step["execute"], step["description"], step["wait_time"], step["execution_time"])
                    f.write(row + '\n')
            f.close()

    def mount_pip(self, position, type, tip_racks, capacity, multi=False, size_tipracks=96):
        self.pips[position]["pip"] = self.ctx.load_instrument(
            type, mount=position, tip_racks=tip_racks)
        self.pips[position]["capacity"] = capacity
        self.pips[position]["count"] = 0
        self.pips[position]["maxes"] = len(tip_racks)*size_tipracks
        if(multi):
            self.pips[position]["increment_tips"] = 8
        else:
            self.pips[position]["increment_tips"] = 1

    def mount_right_pip(self, type, tip_racks, capacity, multi=False):
        self.mount_pip("right", type, tip_racks, capacity)

    def mount_left_pip(self, type, tip_racks, capacity, multi=False):
        self.mount_pip("left", type, tip_racks, capacity)

    def get_current_pip(self):
        
        return self.pips[self.selected_pip]["pip"]

    def get_pip_count(self):
        return self.pips[self.selected_pip]["count"]

    def reset_pip_count(self,pip):       
        pip.reset_tipracks()
        self.pips[self.selected_pip]["count"] = 0

    def add_pip_count(self):
        self.pips[self.selected_pip]["count"] + \
            self.pips[self.selected_pip]["increment_tips"]

    def get_pip_maxes(self):
        return self.pips[self.selected_pip]["maxes"]

    def get_pip_capacity(self):
        return self.pips[self.selected_pip]["capacity"]

    def set_pip(self, position):
        self.selected_pip = position

    def custom_mix(self, reagent, location, vol, rounds, mix_height, blow_out=False,
                   source_height=3, post_dispense=0, x_offset=[0, 0],touch_tip=False):
        '''
        Function for mixing a given [vol] in the same [location] a x number of [rounds].
        blow_out: Blow out optional [True,False]
        x_offset = [source, destination]
        source_height: height from bottom to aspirate
        mix_height: height from bottom to dispense
        '''
        pip = self.get_current_pip()
        vol = vol-1
        if mix_height == 0:
            mix_height = 3
        pip.aspirate(1, location=location.bottom(
            z=source_height).move(Point(x=x_offset[0])), rate=reagent.flow_rate_aspirate_mix)
        for _ in range(rounds):
            pip.aspirate(vol, location=location.bottom(
                z=source_height).move(Point(x=x_offset[0])), rate=reagent.flow_rate_aspirate_mix)
            pip.dispense(vol, location=location.bottom(
                z=mix_height).move(Point(x=x_offset[1])), rate=reagent.flow_rate_dispense_mix)
        pip.dispense(1, location=location.bottom(
            z=mix_height).move(Point(x=x_offset[1])), rate=reagent.flow_rate_dispense_mix)
        if blow_out == True:
            pip.blow_out(location.top(z=-2))  # Blow out
        if post_dispense > 0:
            pip.dispense(post_dispense, location.top(z=-2))
        
        if touch_tip == True:
            pip = self.get_current_pip()
            pip.touch_tip(speed=20, v_offset=-5, radius=0.9)

    def pick_up(self, position=None):
        pip = self.get_current_pip()
        
        if not self.ctx.is_simulating():
            if self.get_pip_count() == self.get_pip_maxes():
                self.ctx.pause('Replace ' + str(pip.max_volume) + 'µl tipracks before \
                resuming.')
                self.reset_pip_count(pip)
        if position != None:
            pip.pick_up_tip(position)
        else:
            if not pip.hw_pipette['has_tip']:
                self.add_pip_count()
                pip.pick_up_tip()

    def drop_tip(self):
        pip = self.get_current_pip()
        pip.drop_tip(home_after=False)
        self.add_pip_count()

    def change_tip(self):
        self.drop_tip()
        self.pick_up()

    def comment(self, comment, add_hash=False):
        hash_string = "#######################################################"
        if (add_hash):
            self.ctx.comment(hash_string)
        self.ctx.comment(('{}').format(comment))
        if (add_hash):
            self.ctx.comment(hash_string)

        if self.ctx.is_simulating():
            if (add_hash):
                print(hash_string)
            print(comment)
            if (add_hash):
                print(hash_string)

    def pause(self, comment):
        self.ctx.pause(comment)
        self.blink(3)
        if self.ctx.is_simulating():
            print("%s\n Press any key to continue " % comment)

    def move_volume(self, reagent, source, dest, vol, 
                    pickup_height, disp_height, air_gap_vol = 0,blow_out=False, touch_tip=False, rinse=False,
                    post_dispense=0,x_offset=[0, 0]):
        # x_offset: list with two values. x_offset in source and x_offset in destination i.e. [-1,1]
        # pickup_height: height from bottom where volume
        # rinse: if True it will do 2 rounds of aspirate and dispense before the tranfer
        # disp_height: dispense height; by default it's close to the top (z=-2), but in case it is needed it can be lowered
        # blow_out, touch_tip: if True they will be done after dispensing

        # Rinse before aspirating
        pipet = self.get_current_pip()
        if rinse == True:
            self.custom_mix(reagent, location=source, vol=vol,
                            rounds=reagent.rinse_loops, blow_out=True, mix_height=1, source_height=pickup_height,
                            x_offset=x_offset)
        # SOURCE
        s = source.bottom(pickup_height).move(Point(x=x_offset[0]))
        # aspirate liquid
        pipet.aspirate(vol, s, rate=reagent.flow_rate_aspirate)
        if air_gap_vol != 0:  # If there is air_gap_vol, switch pipette to slow speed
            pipet.aspirate(air_gap_vol, source.top(z=-2),
                           rate=reagent.flow_rate_aspirate)  # air gap
        # GO TO DESTINATION
        drop = dest.top(z=disp_height).move(Point(x=x_offset[1]))
        pipet.dispense(vol + air_gap_vol, drop,
                       rate=reagent.flow_rate_dispense)  # dispense all
        # pause for x seconds depending on reagent
        self.ctx.delay(seconds=reagent.delay)
        if blow_out == True:
            pipet.blow_out(dest.top(z=-2))
        if post_dispense >0:
            pipet.dispense(post_dispense, dest.top(z=-2))
        if touch_tip == True:
            pipet.touch_tip(speed=20, v_offset=-5, radius=0.9)

    def start_lights(self):
        self.ctx._hw_manager.hardware.set_lights(
            rails=True)  # set lights off when using MMIX

    def stop_lights(self):
        self.ctx._hw_manager.hardware.set_lights(
            rails=False)  # set lights off when using MMIX

    def blink(self, blink_number=3):
        for i in range(blink_number):
            self.stop_lights()
            # ctx._hw_manager.hardware.set_button_light(1,0,0)
            time.sleep(0.3)
            self.start_lights()
            # ctx._hw_manager.hardware.set_button_light(0,0,1)
            time.sleep(0.3)
            self.stop_lights()
