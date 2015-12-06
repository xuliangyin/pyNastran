"""
All dynamic loads are defined in this file.  This includes:

 * DLOAD
 * TLOAD1
 * TLOAD2
 * RLOAD1
 * RLOAD2
"""
from __future__ import (nested_scopes, generators, division, absolute_import,
                        print_function, unicode_literals)
from six import integer_types
from six.moves import zip, range
from scipy.interpolate import interp1d
from numpy import array, exp, pi

from pyNastran.bdf.field_writer_8 import set_blank_if_default
#from pyNastran.bdf.cards.baseCard import BaseCard
from pyNastran.bdf.bdfInterface.assign_type import (integer, integer_or_blank,
    double_or_blank, integer_string_or_blank, string_or_blank,
    integer_double_or_blank)
from pyNastran.bdf.field_writer_8 import print_card_8
from pyNastran.bdf.field_writer_16 import print_card_16
from pyNastran.bdf.field_writer_double import print_card_double
from pyNastran.bdf.cards.loads.loads import TabularLoad, LoadCombination


class DLOAD(LoadCombination):
    type = 'DLOAD'

    def __init__(self, card=None, data=None, comment=''):
        LoadCombination.__init__(self, card, data)
        if comment:
            self._comment = comment

    def cross_reference(self, model):
        load_ids2 = []
        msg = ' which is required by %s=%s' % (self.type, self.sid)
        for load_id in self.loadIDs:
            load_id2 = model.get_dload_entries(load_id, msg=msg)
            load_ids2.append(load_id2)
        self.loadIDs = load_ids2
        self.loadIDs_ref = self.loadIDs

    def uncross_reference(self):
        self.loadIDs = [self.LoadID(load) for load in self.loadIDs]
        del self.loadIDs_ref

    def raw_fields(self):
        list_fields = ['DLOAD', self.sid, self.scale]
        for (scale_factor, load_id) in zip(self.scaleFactors, self.loadIDs):
            list_fields += [scale_factor, self.LoadID(load_id)]
        return list_fields

    def repr_fields(self):
        return self.raw_fields()

    def write_card(self, size=8, is_double=False):
        card = self.raw_fields()
        if size == 16:
            return self.comment + print_card_16(card)
        return self.comment + print_card_8(card)


class RLOAD1(TabularLoad):
    r"""
    Defines a frequency-dependent dynamic load of the form
    for use in frequency response problems.

    .. math::
      \left\{ P(f)  \right\}  = \left\{A\right\} [ C(f)+iD(f)]
         e^{  i \left\{\theta - 2 \pi f \tau \right\} }

    +--------+-----+----------+-------+--------+----+----+------+
    | RLOAD1 | SID | EXCITEID | DELAY | DPHASE | TC | TD | TYPE |
    +--------+-----+----------+-------+--------+----+----+------+
    | RLOAD1 | 5   | 3        |       |        | 1  |    |      |
    +--------+-----+----------+-------+--------+----+----+------+
    """
    type = 'RLOAD1'

    def __init__(self, card=None, data=None, comment=''):
        TabularLoad.__init__(self, card, data)
        if comment:
            self._comment = comment
        if card:
            self.sid = integer(card, 1, 'sid')
            self.exciteID = integer(card, 2, 'exciteID')
            self.delay = integer_double_or_blank(card, 3, 'delay', 0)
            self.dphase = integer_double_or_blank(card, 4, 'dphase')
            self.tc = integer_double_or_blank(card, 5, 'tc', 0)
            self.td = integer_double_or_blank(card, 6, 'td', 0)
            self.Type = integer_string_or_blank(card, 7, 'Type', 'LOAD')
            assert self.tc > 0 or self.td > 0, 'either RLOAD TC or TD > 0; tc=%s td=%s' % (tc, td)

            if self.Type in [0, 'L', 'LO', 'LOA', 'LOAD']:
                self.Type = 'LOAD'
            elif self.Type in [1, 'D', 'DI', 'DIS', 'DISP']:
                self.Type = 'DISP'
            elif self.Type in [2, 'V', 'VE', 'VEL', 'VELO']:
                self.Type = 'VELO'
            elif self.Type in [3, 'A', 'AC', 'ACC', 'ACCE']:
                self.Type = 'ACCE'
            else:
                msg = 'invalid RLOAD1 type  Type=%r' % self.Type
                raise RuntimeError(msg)
            assert len(card) <= 8, 'len(RLOAD1 card) = %i' % len(card)
        else:
            raise NotImplementedError(data)

    def cross_reference(self, model):
        msg = ' which is required by RLOAD1 sid=%s' % (self.sid)
        if self.tc > 0:
            self.tc = model.Table(self.tc, msg=msg)
            self.tc_ref = self.tc
        if self.td > 0:
            self.td = model.Table(self.td, msg=msg)
            self.td_ref = self.td
        if isinstance(self.delay, integer_types) and self.delay > 0:
            self.delay = model.DELAY(self.delay_id, msg=msg)
            self.delay_ref = self.delay

    def uncross_reference(self):
        self.tc = self.Tc()
        self.td = self.Td()
        self.delay = self.delay_id
        if self.tc > 0:
            del self.tc_ref
        if self.td > 0:
            del self.td_ref
        if isinstance(self.delay, integer_types) and self.delay > 0:
            del self.delay_ref

    def getLoads(self):
        self.deprecated('getLoads()', 'get_loads()', '0.8')
        return self.get_loads()

    def get_loads(self):
        return [self]

    def Tc(self):
        if self.tc in [0, 0.0]:
            return 0
        elif isinstance(self.tc, integer_types):
            return self.tc
        return self.tc.tid

    def Td(self):
        if self.td in [0, 0.0]:
            return 0
        elif isinstance(self.td, integer_types):
            return self.td
        return self.td.tid

    @property
    def delay_id(self):
        if self.delay in [0, 0.0]:
            return 0
        elif isinstance(self.delay, (integer_types, float)):
            return self.delay
        return self.delay_ref.sid

    def get_load_at_freq(self, freq, scale=1.):
        # A = 1. # points to DAREA or SPCD
        if isinstance(self.tc, float):
            c = float(self.tc)
        elif self.tc == 0:
            c = 0.
        else:
            cxy = array(self.tc.table.table)
            fc = cxy[:, 0]
            yc = cxy[:, 1]
            assert fc.shape == yc.shape, 'fc.shape=%s yc.shape=%s' % (str(fc.shape), str(yc.shape))
            c = interp1d(fc, yc)(freq)

        if isinstance(self.td, float):
            d = float(self.td)
        elif self.td == 0:
            d = 0.
        else:
            dxy = array(self.td.table.table)
            fd = dxy[:, 0]
            yd = dxy[:, 1]
            assert fd.shape == yd.shape, 'fd.shape=%s yd.shape=%s' % (str(fd.shape), str(yd.shape))
            d = interp1d(fd, yd)(freq)

        if isinstance(self.dphase, float):
            dphase = self.dphase
        elif self.dphase == 0 or self.dphase is None:
            dphase = 0.0
        else:
            #print('DPHASE is not supported')
            nids, comps, dphases = self.dphase.get_dphase_at_freq(freq)
            assert len(dphases) == 1, dphases
            dphase = dphases[0]

        if isinstance(self.delay, float):
            tau = self.delay
        elif self.delay == 0 or self.dphase is None:
            tau = 0.0
        else:
            tau = self.delay.get_delay_at_freq(freq)

        out = (c + 1.j * d) * exp(dphase - 2 * pi * freq * tau)
        return out

    def raw_fields(self):
        list_fields = ['RLOAD1', self.sid, self.exciteID, self.delay_id, self.dphase,
                       self.Tc(), self.Td(), self.Type]
        return list_fields

    def repr_fields(self):
        Type = set_blank_if_default(self.Type, 'LOAD')
        list_fields = ['RLOAD1', self.sid, self.exciteID, self.delay_id, self.dphase,
                       self.Tc(), self.Td(), Type]
        return list_fields

    def write_card(self, size=8, is_double=False):
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        if is_double:
            return self.comment + print_card_double(card)
        return self.comment + print_card_16(card)


class RLOAD2(TabularLoad):
    r"""
    Defines a frequency-dependent dynamic load of the form
    for use in frequency response problems.

    .. math:: \left\{ P(f)  \right\}  = \left\{A\right\} * B(f)
        e^{  i \left\{ \phi(f) + \theta - 2 \pi f \tau \right\} }

    +--------+-----+----------+-------+--------+----+----+------+
    | RLOAD2 | SID | EXCITEID | DELAY | DPHASE | TB | TP | TYPE |
    +--------+-----+----------+-------+--------+----+----+------+
    | RLOAD2 | 5   | 3        |       |        | 1  |    |      |
    +--------+-----+----------+-------+--------+----+----+------+
    """
    type = 'RLOAD2'

    def __init__(self, card=None, data=None, comment=''):
        TabularLoad.__init__(self, card, data)
        if comment:
            self._comment = comment
        if card:
            self.sid = integer(card, 1, 'sid')
            self.exciteID = integer(card, 2, 'exciteID')
            self.delay = integer_double_or_blank(card, 3, 'delay', 0)
            self.dphase = integer_double_or_blank(card, 4, 'dphase')
            self.tb = integer_or_blank(card, 5, 'tb', 0)
            self.tp = integer_or_blank(card, 6, 'tp', 0)
            self.Type = integer_string_or_blank(card, 7, 'Type', 'LOAD')

            if self.Type in [0, 'L', 'LO', 'LOA', 'LOAD']:
                self.Type = 'LOAD'
            elif self.Type in [1, 'D', 'DI', 'DIS', 'DISP']:
                self.Type = 'DISP'
            elif self.Type in [2, 'V', 'VE', 'VEL', 'VELO']:
                self.Type = 'VELO'
            elif self.Type in [3, 'A', 'AC', 'ACC', 'ACCE']:
                self.Type = 'ACCE'
            else:
                msg = 'invalid RLOAD2 type  Type=|%s|' % self.Type
                raise RuntimeError(msg)
            assert len(card) <= 8, 'len(RLOAD2 card) = %i' % len(card)
        else:
            raise NotImplementedError(data)

    def get_load_at_freq(self, freq, scale=1.):
        # A = 1. # points to DAREA or SPCD
        if isinstance(self.tb, float):
            b = self.tb
        elif self.tb == 0:
            b = 0.0
        else:
            bxy = array(self.tb_ref.table.table)
            fb = bxy[:, 0]
            yb = bxy[:, 1]
            assert fb.shape == yb.shape, 'fb.shape=%s yb.shape=%s' % (str(fb.shape), str(yb.shape))
            b = interp1d(fb, yb)(freq)

        if isinstance(self.tp, float):
            p = self.tp
        elif self.tp == 0:
            p = 0.0
        else:
            pxy = array(self.tp_ref.table.table)
            fp = pxy[:, 0]
            yp = pxy[:, 1]
            assert fp.shape == yp.shape, 'fp.shape=%s yp.shape=%s' % (str(fp.shape), str(yp.shape))
            p = interp1d(fp, yp)(freq)

        if isinstance(self.dphase, float):
            dphase = self.dphase
        elif self.dphase == 0 or self.dphase is None:
            dphase = 0.0
        else:
            #raise NotImplementedError('DPHASE is not supported')
            dphase = self.dphase_ref.get_dphase_at_freq(freq)

        if isinstance(self.delay, float):
            tau = self.delay
        elif self.delay == 0:
            tau = 0.0
        else:
            #raise NotImplementedError('DELAY is not supported')
            nids, comps, taus = self.delay_ref.get_delay_at_freq(freq)
            assert len(taus) == 1, taus
            tau = taus[0]

        try:
            out = b * exp(1.j * p + dphase - 2 * pi * freq * tau)
        except TypeError:
            print('b =', b)
            print('p =', p)
            print('dphase =', dphase)
            print('freq =', freq)
            print('tau =', tau)
            raise
        return out

    def cross_reference(self, model):
        msg = ' which is required by RLOAD2=%s' % (self.sid)
        if self.tb:
            self.tb = model.Table(self.tb, msg=msg)
            self.tb_ref = self.tb
        if self.tp:
            self.tp = model.Table(self.tp, msg=msg)
            self.tp_ref = self.tp
        if self.delay > 0:
            self.delay = model.DELAY(self.delay, msg=msg)
            self.delay_ref = self.delay

    def uncross_reference(self):
        self.tb = self.Tb()
        self.tp = self.Tp()
        self.delay = self.delay_id
        if self.tb > 0:
            del self.tb_ref
        if self.tp > 0:
            del self.tp_ref
        if self.delay > 0:
            del self.delay_ref

    def getLoads(self):
        self.deprecated('getLoads()', 'get_loads()', '0.8')
        return self.get_loads()

    def get_loads(self):
        return [self]

    def LoadID(self):
        return self.sid

    def Tb(self):
        if self.tb == 0:
            return 0
        elif isinstance(self.tb, integer_types):
            return self.tb
        return self.tb_ref.tid

    def Tp(self):
        if self.tp == 0:
            return 0
        elif isinstance(self.tp, integer_types):
            return self.tp
        return self.tp_ref.tid

    @property
    def delay_id(self):
        if self.delay in [0, 0.]:
            return 0
        elif isinstance(self.delay, integer_types):
            return self.delay
        return self.delay.sid

    def raw_fields(self):
        list_fields = ['RLOAD2', self.sid, self.exciteID, self.delay_id, self.dphase,
                       self.Tb(), self.Tp(), self.Type]
        return list_fields

    def repr_fields(self):
        Type = set_blank_if_default(self.Type, 0.0)
        list_fields = ['RLOAD2', self.sid, self.exciteID, self.delay_id, self.dphase,
                       self.Tb(), self.Tp(), Type]
        return list_fields

    def write_card(self, size=8, is_double=False):
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        if is_double:
            return self.comment + print_card_double(card)
        return self.comment + print_card_16(card)


class TLOAD1(TabularLoad):
    r"""
    Transient Response Dynamic Excitation, Form 1

    Defines a time-dependent dynamic load or enforced motion of the form:

    .. math::
      \left\{ P(t) \right\} = \left\{ A \right\} \cdot F(t-\tau)

    for use in transient response analysis.
    """
    type = 'TLOAD1'

    def __init__(self, card=None, data=None, comment=''):
        TabularLoad.__init__(self, card, data)
        if comment:
            self._comment = comment
        if card:
            #: load ID
            self.sid = integer(card, 1, 'sid')

            #: Identification number of DAREA or SPCD entry set or a thermal load
            #: set (in heat transfer analysis) that defines {A}. (Integer > 0)
            self.exciteID = integer(card, 2, 'exciteID')

            #: If it is a non-zero integer, it represents the
            #: identification number of DELAY Bulk Data entry that defines .
            #: If it is real, then it directly defines the value of that will
            #: be used for all degrees-of-freedom that are excited by this
            #: dynamic load entry.  See also Remark 9. (Integer >= 0,
            #: real or blank)
            self.delay = integer_double_or_blank(card, 3, 'delay', 0)

            #: Defines the type of the dynamic excitation. (LOAD,DISP, VELO, ACCE)
            self.Type = integer_string_or_blank(card, 4, 'Type', 'LOAD')

            #: Identification number of TABLEDi entry that gives F(t). (Integer > 0)
            self.tid = integer(card, 5, 'tid')

            #: Factor for initial displacements of the enforced degrees-of-freedom.
            #: (Real; Default = 0.0)
            self.us0 = double_or_blank(card, 6, 'us0', 0.0)

            #: Factor for initial velocities of the enforced degrees-of-freedom.
            #: (Real; Default = 0.0)
            self.vs0 = double_or_blank(card, 7, 'vs0', 0.0)
            if   self.Type in [0, 'L', 'LO', 'LOA', 'LOAD']:
                self.Type = 'LOAD'
            elif self.Type in [1, 'D', 'DI', 'DIS', 'DISP']:
                self.Type = 'DISP'
            elif self.Type in [2, 'V', 'VE', 'VEL', 'VELO']:
                self.Type = 'VELO'
            elif self.Type in [3, 'A', 'AC', 'ACC', 'ACCE']:
                self.Type = 'ACCE'
            else:
                msg = 'invalid TLOAD1 type  Type=|%s|' % self.Type
                raise RuntimeError(msg)
            assert len(card) <= 8, 'len(TLOAD1 card) = %i' % len(card)
        else:
            raise NotImplementedError(data)

    def getLoads(self):
        self.deprecated('getLoads()', 'get_loads()', '0.8')
        return self.get_loads()

    def get_loads(self):
        return [self]

    def cross_reference(self, model):
        msg = ' which is required by %s=%s' % (self.type, self.sid)
        if self.tid:
            self.tid = model.Table(self.tid, msg=msg)
            self.tid_ref = self.tid
        if isinstance(self.delay, integer_types) and self.delay > 0:
            self.delay = model.DELAY(self.delay, msg=msg)
            self.delay_ref = self.delay

    def uncross_reference(self):
        self.tid = self.Tid()
        self.delay = self.delay_id
        if self.tid > 0:
            del self.tid_ref
        if self.delay > 0:
            del self.delay_ref

    def safe_cross_reference(self, model, debug=True):
        msg = ' which is required by %s=%s' % (self.type, self.sid)
        if self.tid:
            #try:
            self.tid = model.Table(self.tid, msg=msg)
            #except
        if isinstance(self.delay, integer_types) and self.delay > 0:
            self.delay = model.DELAY(self.delay_id, msg=msg)

    def Tid(self):
        if self.tid == 0:
            return 0
        elif isinstance(self.tid, integer_types):
            return self.tid
        return self.tid_ref.tid

    @property
    def delay_id(self):
        if self.delay in [0, 0.]:
            return 0
        elif isinstance(self.delay, integer_types):
            return self.delay
        return self.delay_ref.sid

    def get_load_at_time(self, time, scale=1.):
        # A = 1. # points to DAREA or SPCD
        xy = array(self.tid.table.table)
        x = xy[:, 0]
        y = xy[:, 1]
        assert x.shape == y.shape, 'x.shape=%s y.shape=%s' % (str(x.shape), str(y.shape))
        f = interp1d(x, y)

        if isinstance(self.delay, float):
            tau = self.delay
        elif self.delay == 0 or self.delay is None:
            tau = 0.0
        else:
            #raise NotImplementedError('DELAY is not supported')
            tau = self.delay.get_delay_at_freq(freq)

        resp = f(time - tau)
        is_spcd = False
        if self.Type == 'VELO' and is_spcd:
            resp[0] = self.us0
        if self.Type == 'ACCE' and is_spcd:
            resp[0] = self.vs0
        return resp

    def raw_fields(self):
        list_fields = ['TLOAD1', self.sid, self.exciteID, self.delay_id, self.Type,
                       self.Tid(), self.us0, self.vs0]
        return list_fields

    def repr_fields(self):
        us0 = set_blank_if_default(self.us0, 0.0)
        vs0 = set_blank_if_default(self.vs0, 0.0)
        list_fields = ['TLOAD1', self.sid, self.exciteID, self.delay_id, self.Type,
                       self.Tid(), us0, vs0]
        return list_fields

    def write_card(self, size=8, is_double=False):
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        if is_double:
            return self.comment + print_card_double(card)
        return self.comment + print_card_16(card)


class TLOAD2(TabularLoad):
    r"""
    Transient Response Dynamic Excitation, Form 1

    Defines a time-dependent dynamic load or enforced motion of the form:

    .. math::
      \left\{ P(t) \right\} = \left\{ A \right\} \cdot F(t-\tau)

    for use in transient response analysis.
    """
    type = 'TLOAD2'

    def __init__(self, card=None, data=None, comment=''):
        TabularLoad.__init__(self, card, data)
        if comment:
            self._comment = comment
        if card:
            #: load ID
            #: SID must be unique for all TLOAD1, TLOAD2, RLOAD1, RLOAD2, and ACSRCE entries.
            self.sid = integer(card, 1, 'sid')

            self.exciteID = integer(card, 2, 'exciteID')
            self.delay = integer_or_blank(card, 3, 'delay', 0)

            #: Defines the type of the dynamic excitation. (Integer; character
            #: or blank; Default = 0)
            self.Type = integer_string_or_blank(card, 4, 'Type', 'LOAD')

            #: Time constant. (Real >= 0.0)
            self.T1 = double_or_blank(card, 5, 'T1', 0.0)
            #if self.delay == 0:
            #self.T1 = double_or_blank(card, 5, 'T1', 0.)
            #else:
            #self.T1 = blank(card, 5, 'T1')

            #: Time constant. (Real; T2 > T1)
            self.T2 = double_or_blank(card, 6, 'T2', self.T1)
            #: Frequency in cycles per unit time. (Real >= 0.0; Default = 0.0)
            self.frequency = double_or_blank(card, 7, 'frequency', 0.)
            #: Phase angle in degrees. (Real; Default = 0.0)
            self.phase = double_or_blank(card, 8, 'phase', 0.)
            #: Exponential coefficient. (Real; Default = 0.0)
            self.c = double_or_blank(card, 9, 'c', 0.)
            #: Growth coefficient. (Real; Default = 0.0)
            self.b = double_or_blank(card, 10, 'b', 0.)
            #: Factor for initial displacements of the enforced degrees-of-freedom.
            #: (Real; Default = 0.0)
            self.us0 = double_or_blank(card, 11, 'us0', 0.)
            #: Factor for initial velocities of the enforced degrees-of-freedom
            #: (Real; Default = 0.0)
            self.vs0 = double_or_blank(card, 12, 'vs0', 0.)

            if self.Type in [0, 'L', 'LO', 'LOA', 'LOAD']:
                self.Type = 'LOAD'
            elif self.Type in [1, 'D', 'DI', 'DIS', 'DISP']:
                self.Type = 'DISP'
            elif self.Type in [2, 'V', 'VE', 'VEL', 'VELO']:
                self.Type = 'VELO'
            elif self.Type in [3, 'A', 'AC', 'ACC', 'ACCE']:
                self.Type = 'ACCE'
            elif self.Type in [5, 6, 7, 12, 13]:
                pass
            else:
                msg = 'invalid TLOAD2 type  Type=|%s|' % self.Type
                raise RuntimeError(msg)
            assert len(card) <= 13, 'len(TLOAD2 card) = %i' % len(card)
        else:
            raise NotImplementedError(data)

    def get_load_at_time(self, time, scale=1.):
        # A = 1. # points to DAREA or SPCD
        xy = array(self.tid.table.table)
        x = xy[:, 0]
        y = xy[:, 1]
        assert x.shape == y.shape, 'x.shape=%s y.shape=%s' % (str(x.shape), str(y.shape))
        f = interp1d(x, y)

        if isinstance(self.delay, float):
            tau = self.delay
        elif self.delay == 0 or self.delay is None:
            tau = 0.0
        else:
            #raise NotImplementedError('DELAY is not supported')
            tau = self.delay.get_delay_at_time(time)
        # return f(time - tau)

        t1 = self.T1 + tau
        t2 = self.T2 + tau
        f = self.frequency
        p = self.phase
        f = zeros(time.shape, dtype=time.dtype)

        i = where(t1 <= time & time <= t2)[0]
        f[i] = time[i] ** b * exp(c * time[i]) * cos(2 * pi * f * time[i] + p)

        is_spcd = False
        resp = f
        if self.Type == 'VELO' and is_spcd:
            f[0] = self.us0
        if self.Type == 'ACCE' and is_spcd:
            f[0] = self.vs0
        return f

    def getLoads(self):
        self.deprecated('getLoads()', 'get_loads()', '0.8')
        return self.get_loads()

    def get_loads(self):
        return [self]

    def cross_reference(self, model):
        msg = ' which is required by TLOAD2 sid=%s' % (self.sid)
        if isinstance(self.delay, integer_types) and self.delay > 0:
            self.delay = model.DELAY(self.delay_id, msg=msg)
            self.delay_ref = self.delay
        # TODO: exciteID

    def safe_cross_reference(self, model, debug=True):
        msg = ' which is required by TLOAD2 sid=%s' % (self.sid)
        if isinstance(self.delay, integer_types) and self.delay > 0:
            self.delay = model.DELAY(self.delay_id, msg=msg)
        # TODO: exciteID

    def uncross_reference(self):
        self.delay = self.delay_id
        if isinstance(self.delay, integer_types) and self.delay > 0:
            del self.delay_ref

    @property
    def delay_id(self):
        if self.delay == 0:
            return 0
        elif isinstance(self.delay, integer_types):
            return self.delay
        return self.delay_ref.sid

    def raw_fields(self):
        list_fields = ['TLOAD2', self.sid, self.exciteID, self.delay_id, self.Type,
                       self.T1, self.T2, self.frequency, self.phase, self.c, self.b,
                       self.us0, self.vs0]
        return list_fields

    def repr_fields(self):
        frequency = set_blank_if_default(self.frequency, 0.0)
        phase = set_blank_if_default(self.phase, 0.0)
        c = set_blank_if_default(self.c, 0.0)
        b = set_blank_if_default(self.b, 0.0)

        us0 = set_blank_if_default(self.us0, 0.0)
        vs0 = set_blank_if_default(self.vs0, 0.0)
        list_fields = ['TLOAD2', self.sid, self.exciteID, self.delay_id, self.Type,
                       self.T1, self.T2, frequency, phase, c, b, us0, vs0]
        return list_fields

    def write_card(self, size=8, is_double=False):
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        if is_double:
            return self.comment + print_card_double(card)
        return self.comment + print_card_16(card)
